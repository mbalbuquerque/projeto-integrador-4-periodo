# API do ColdTrack

> Documentação interativa (Swagger UI, com "Try it out"): <https://func-coldtrack-7319.azurewebsites.net/api/docs>.
> Especificação OpenAPI 3.0: [`cloud/function/openapi.json`](../cloud/function/openapi.json)
> (publicada em `/api/openapi.json`). Este arquivo é a referência em texto, com as regras em detalhe.

Referência das rotas da Azure Function (`cloud/function/function_app.py`). As regras de
validação estão em `cadastros.py` (cadastros do painel) e `contrato.py` (telemetria e
filtros).

Base: `https://func-coldtrack-7319.azurewebsites.net/api`
(local: `http://localhost:7071/api`).

## Convenções

- Corpo e resposta em JSON (`application/json`, UTF-8).
- **Erro**: sempre `{"erros": ["mensagem", ...]}`. Erros de campo vêm prefixados com o nome
  do campo (`"email: formato inválido"`), para a tela mostrar ao lado do campo.
- `204` não tem corpo.
- A Function é publicada com nível de acesso anônimo: quem confere o acesso é o próprio
  código, em toda chamada.

### Autenticação

| tipo | como | usado por |
|---|---|---|
| chave do sensor | header `x-device-key: <chave>` | `POST /telemetria`, `POST /heartbeat` |
| token do painel | header `Authorization: Bearer <token>` | rotas do painel, `POST /assistente` e `POST /sair` |
| nenhuma | — | `POST /empresas`, `POST /login`, `GET /perfis`, `POST /chat`, `GET /docs`, `GET /openapi.json` |

O token é um JWT HS256 válido por 8 horas, emitido por `POST /login`, `POST /empresas` e
`POST /senha`. A cada chamada a API confere o usuário no banco: usuário removido, senha
trocada ou redefinida, `POST /sair` (versão da sessão diferente) e empresa diferente
derrubam o token. O perfil considerado é o atual do usuário, não o de quando o token foi
emitido; cadastro sem perfil ou sem empresa recebe `403`.

### Limites de uso

Contados no Cosmos (container `limites`), somando todas as instâncias da Function. O IP é o
do header `X-Azure-ClientIP` ou, sem ele, o último item do `X-Forwarded-For` (o que o Azure
acrescenta; os anteriores podem ter sido escritos pelo cliente).

| rota | limite | resposta |
|---|---|---|
| `POST /login` | 20 tentativas erradas por IP a cada 15 min (em qualquer conta) | `429` |
| `POST /login` | por conta: espera de 1 min a partir da 5ª senha errada seguida, dobrando até 15 min | `401` (mesma resposta de senha errada) |
| `POST /empresas` | 5 cadastros por hora por IP (pedido inválido não conta) | `429` |
| `POST /senha` | por conta, junto com o login: espera de 1 min a partir da 5ª senha atual errada seguida, dobrando até 15 min | `429` |
| `DELETE /empresa` | 5 pedidos bem formados por hora por gestor; a senha errada conta na mesma espera do login | `429` |
| `POST /chat` | 10 perguntas por minuto por IP; 2000 por dia no site todo | `429` |
| `POST /assistente` | 15 perguntas por minuto por usuário; 300 por dia por empresa | `429` |
| `GET /motorista` | 30 consultas por minuto por usuário (a tela consulta a cada 20 s) | `429` |
| `POST /heartbeat` | 6 por minuto por sensor (a placa envia 3: um a cada 20 s) | `429` |

As janelas são fixas (o minuto, os 15 min ou o dia corrente, em UTC).

### Códigos comuns

| código | quando | mensagem |
|---|---|---|
| `400` | corpo não é JSON | `corpo não é JSON válido` |
| `400` | corpo não é objeto | `corpo deve ser um objeto JSON` |
| `401` | sem token, token inválido/expirado ou sessão derrubada | `faça login para continuar` |
| `403` | perfil sem permissão | `seu perfil não tem acesso a esta ação` |
| `404` | item inexistente ou de outra empresa (as duas respondem igual) | `não encontrado` / `dispositivo não encontrado` |

Perfis: `operador` (consulta), `gestor` (consulta e cadastra) e `motorista` (só `GET /motorista`,
com o veículo vinculado à conta, a própria conta: `GET /eu`, `POST /senha`, `POST /sair`, e a
inscrição nos alertas push: `POST/DELETE /push/inscricao`; as demais rotas do painel respondem
`403`).

## Sensor

### `POST /telemetria`

Acesso: chave do sensor (`x-device-key`). A chave só vale para o próprio `deviceId`.

```json
{"deviceId": "coldtrack-01", "temperatura": 12.4, "umidade": 81.0, "rssi": -58, "medidoEm": 1790000000}
```

| campo | regra |
|---|---|
| `deviceId` | texto de 3 a 40 caracteres: letras, números, `_` ou `-` (gravado em minúsculas) |
| `temperatura` | número de -40 a 80 (°C), obrigatório |
| `umidade` | número de 0 a 100 (%), obrigatório |
| `rssi` | número de -120 a 0, ou `null` (o simulador Wokwi reporta valor positivo); a chave é obrigatória |
| `medidoEm` | opcional; epoch UTC em segundos. Até 5 min no futuro e até 7 dias no passado |
| `temperaturaBruta`, `umidadeBruta` | opcionais; leitura antes do filtro de mediana da placa, na mesma faixa de `temperatura`/`umidade`. Gravadas junto só para auditoria; status e alertas usam o valor filtrado |

Booleanos não valem como número; `NaN` é rejeitado; campo não previsto é erro.

| resposta | corpo |
|---|---|
| `201` | `{"id", "status", "perfil", "faixa": {"min", "max", "margem"}}` |
| `200` | `{"id", "duplicada": true}`: reenvio de leitura já gravada com os mesmos valores |
| `400` | erros de validação |
| `401` | `dispositivo não registrado ou chave inválida` |
| `409` | já existe leitura do sensor nesse segundo com outros valores |

Com `medidoEm`, o id da leitura é `<deviceId>~<medidoEm>`; sem ele, um UUID. A leitura
nunca é sobrescrita.

**Classificação** (`status`): pelo perfil de carga do veículo que usa o sensor (sensor sem
veículo usa `demonstrativo`). Dentro de `[min, max]` é `NORMAL`; até `margem` °C fora é
`ATENCAO`; além disso, `CRITICO`. `min` nulo significa sem limite inferior. O sensor usa a
`faixa` devolvida para acender os LEDs.

**Alerta push**: quando a leitura piora de faixa, os operadores e gestores inscritos da empresa e
os motoristas inscritos vinculados ao veículo do sensor recebem uma notificação (ver
[Alertas push](#alertas-push-push)).

### `POST /heartbeat`

Acesso: chave do sensor (`x-device-key`), igual a `POST /telemetria`. Sinal de vida da placa
no ciclo (20 s) em que ela não tem leitura válida para enviar; hoje o único motivo é o sensor
em falha (leitura do DHT falhou).

```json
{"deviceId": "coldtrack-01", "motivo": "sensor_falha", "fw": "2026.11.17.2", "rssi": -61, "seq": 1532}
```

| campo | regra |
|---|---|
| `deviceId` | igual à telemetria |
| `motivo` | `sensor_falha` |
| `fw` | versão do firmware: 1 a 32 caracteres, letras, números, `.`, `_` ou `-` |
| `rssi` | opcional; inteiro de -120 a 0, ou `null` |
| `seq` | opcional; número de sequência da **última leitura** produzida pela placa (o heartbeat não gasta número, para não abrir lacuna falsa em `GET /leituras`) |

| resposta | corpo |
|---|---|
| `200` | `{"sensor": "falha", "sensorFalhaDesde": "<ISO 8601>"}` |
| `400` | erros de validação |
| `401` | `dispositivo não registrado ou chave inválida` |
| `429` | `muitos heartbeats seguidos. Tente de novo em 1 min.` |

O heartbeat **não cria leitura**: leitura inválida nunca é gravada como válida. Ele grava no
cadastro do dispositivo o horário do heartbeat (conta como último contato em
`GET /dispositivos`), o motivo, a versão do firmware, o RSSI e `sensorFalhaDesde`, que é mantido
desde o primeiro heartbeat da falha até chegar uma leitura válida (`POST /telemetria`), que
encerra a falha. A placa não guarda heartbeat na fila offline: sinal de vida atrasado não diz
nada sobre o agora.

## Acesso

### `GET /perfis`

Acesso: aberto. Resposta `200`:

```json
{"perfis": [{"id": "demonstrativo", "nome": "Demonstrativo (protótipo)", "min": null, "max": 15.0, "margem": 5.0},
            {"id": "manga", "nome": "Manga", "min": 10.0, "max": 13.0, "margem": 3.0},
            {"id": "uva", "nome": "Uva de mesa", "min": -1.0, "max": 0.0, "margem": 2.0}]}
```

### `POST /empresas`

Acesso: aberto. Cria a empresa e o primeiro usuário, com perfil `gestor`.

```json
{"empresa": "Transportes Exemplo", "nome": "Maria", "email": "maria@exemplo.com", "senha": "********"}
```

| campo | regra |
|---|---|
| `empresa` | obrigatório, até 80 caracteres |
| `nome` | obrigatório, até 80 caracteres |
| `email` | obrigatório, até 120 caracteres, formato de e-mail (gravado em minúsculas, é o id do usuário) |
| `senha` | 8 a 128 caracteres |

Respostas: `201 {"token", "usuario": {"id", "nome", "perfil", "empresaId", "empresa"}}`;
`400` validação; `409` `já existe uma conta com esse e-mail`; `429` `muitos cadastros deste IP. Tente de novo em 1 hora.` O id da empresa é gerado
(`E-` + 8 caracteres hexadecimais).

### `POST /login`

Acesso: aberto.

```json
{"email": "maria@exemplo.com", "senha": "********"}
```

| resposta | corpo |
|---|---|
| `200` | `{"token", "usuario": {"id", "nome", "perfil", "empresaId", "empresa"}}` |
| `401` | `e-mail ou senha incorretos. Se errou várias vezes, aguarde alguns minutos.` |
| `429` | `muitas tentativas de login erradas. Aguarde alguns minutos.` (20 erros do mesmo IP em 15 min) |

O `401` é igual, na mensagem e no tempo, para e-mail inexistente, senha errada e conta em
espera: a resposta não revela quem tem conta. A partir da 5ª senha errada seguida a conta
fica em espera (1 min, depois 2, 4, 8 e no máximo 15 min); durante a espera nem a senha
certa entra, e as tentativas não aumentam a espera. Falhas com mais de 24 h são esquecidas;
o gestor também tira a conta da espera ao redefinir a senha (`PUT /usuarios/{email}`).

### `GET /eu`

Acesso: operador, gestor, motorista. Resposta `200`: `{"id", "nome", "perfil", "empresaId", "empresa"}`,
mais `veiculo` (código do veículo vinculado) quando o perfil é `motorista`. A resposta do login
traz o mesmo objeto em `usuario`.

### `POST /senha`

Acesso: operador, gestor, motorista. Troca a própria senha.

```json
{"atual": "********", "nova": "********"}
```

`nova` com 8 a 128 caracteres e diferente de `atual`. Respostas: `200 {"token", "usuario"}`
(novo token; os anteriores param de valer); `400` validação ou `atual: senha atual incorreta`; `429` `muitas tentativas de senha atual erradas. Aguarde alguns minutos.` (conta em espera: a senha atual errada conta na mesma espera do login e, durante ela, nem a senha certa troca; ao trocar com sucesso a contagem zera).

### `POST /sair`

Acesso: operador, gestor, motorista. Sem corpo. Encerra **todas** as sessões do usuário (todos os
aparelhos): sobe a versão da sessão e todo token já emitido passa a receber `401`.
Resposta: `204`. O painel deve chamar antes de apagar o token guardado no navegador.
Também apaga as inscrições de alerta push do usuário.

### `DELETE /empresa`

Acesso: gestor, só da própria empresa (a do token). Exclui a empresa e **todos** os dados dela
(direito de eliminação da LGPD, art. 18, VI). Não há como desfazer.

```json
{"confirmacao": "Transportes Exemplo", "senha": "********"}
```

| campo | regra |
|---|---|
| `confirmacao` | o nome da empresa como foi cadastrado, ou o código dela (`empresaId`, de `GET /eu`); maiúsculas e espaços nas pontas não importam |
| `senha` | a senha atual do gestor (até 128 caracteres) |

Ordem da exclusão: (1) sobe a versão da sessão e tira o push dos outros usuários, que saem na
hora e não cadastram nada durante a exclusão; (2) sensores, cuja chave para de valer; (3) todas
as leituras da empresa, inclusive de sensores removidos antes; (4) viagens; (5) veículos;
(6) os outros usuários; (7) a empresa; (8) por último, o gestor que pediu. Item que já sumiu é
ignorado.

| resposta | corpo |
|---|---|
| `200` | `{"excluida": true, "removidos": {"dispositivos": 1, "leituras": 240, "viagens": 1, "veiculos": 1, "usuarios": 2, "empresas": 1}}` (contagem deste pedido) |
| `202` | `{"excluida": false, "removidos": {...}, "mensagem": "exclusão em andamento: repita o mesmo pedido para continuar de onde parou."}` |
| `400` | validação; `confirmacao: não confere com o nome da empresa`; `senha: senha atual incorreta` |
| `401` | sem token ou sessão derrubada (inclusive depois da exclusão concluída) |
| `403` | perfil diferente de gestor |
| `429` | `muitos pedidos de exclusão. Tente de novo em 1 hora.` ou conta em espera por senha errada |

Cada pedido trabalha até 120 s. Empresa com muitas leituras pode precisar de mais de um pedido:
o `202` diz para repetir, e o pedido seguinte continua de onde o anterior parou. Um pedido que
falhou no meio (erro do banco) também é repetido do mesmo jeito. Enquanto a empresa existe, a
confirmação aceita o nome; depois que ela foi apagada (falha entre a empresa e o gestor), só o
código. O log registra só o código da empresa e as contagens, sem e-mail nem nome.

## Alertas push (`/push`)

Web Push padrão (VAPID): o navegador do usuário (Chrome/Edge/Firefox no Android ou no
computador; Safari no iPhone com o painel instalado na tela inicial, iOS 16.4 ou mais novo) cria
uma inscrição no serviço de push dele e o painel a envia para a API. Sem serviço pago: a API
assina cada envio com a chave privada VAPID e o serviço de push do navegador entrega.

| método e rota | acesso | corpo | resposta |
|---|---|---|---|
| `GET /push/chave` | público | — | `200 {"chave"}` (chave pública VAPID, base64url); `503` sem chaves configuradas |
| `POST /push/inscricao` | operador, gestor, motorista | `PushSubscription.toJSON()`: `{"endpoint", "keys": {"p256dh", "auth"}}` | `201 {"inscricoes": n}` |
| `DELETE /push/inscricao` | operador, gestor, motorista | `{"endpoint"}` | `204` (também quando o endpoint não era do usuário) |

- `endpoint` precisa ser `https` em um serviço de push conhecido (`fcm.googleapis.com`,
  `*.push.services.mozilla.com`, `*.push.apple.com`, `*.notify.windows.com`); outro endereço dá
  `400 endpoint: serviço de push não reconhecido`. A API só faz POST para esses hosts.
- A inscrição fica no documento do usuário (campo `push`, até 10 aparelhos; o mais antigo sai).
  O mesmo endpoint não se repete, e se estava em outra conta (aparelho compartilhado) sai de lá.
- `POST /sair` apaga todas as inscrições do usuário; remover o usuário apaga junto.

**Quando o push sai** (no `POST /telemetria`, depois de gravar a leitura nova):

- só quando a faixa **piora** em relação à leitura anterior do mesmo sensor pelo horário da
  medição: `NORMAL → ATENCAO`, `NORMAL → CRITICO`, `ATENCAO → CRITICO`. Mesma faixa ou melhora
  não avisam; o reenvio duplicado (`200 duplicada`) não chega a esse ponto;
- no máximo 1 push por sensor e faixa a cada 10 min (contador no container `limites`), para a
  leitura que oscila na borda da faixa não virar uma notificação a cada 20 s;
- leitura medida há mais de 30 min (fila offline do sensor chegando depois) não avisa;
- vai para as inscrições dos usuários da **empresa do sensor**: operador e gestor recebem de
  todos os sensores da empresa; o **motorista só do sensor do veículo vinculado a ele** (campo
  `veiculo` do cadastro, relido a cada leitura: trocar o veículo troca os alertas). Motorista
  sem veículo, ou sensor que não está em veículo, não gera push para motorista.

Conteúdo da notificação (JSON cifrado de ponta a ponta, só o navegador lê):
`{"titulo", "corpo", "url", "tag", "status", "deviceId"}`, com `url` `/alertas?veiculo=<código>`
(ou `/alertas` se o sensor não está em veículo) para operador e gestor, e `/motorista` para o
motorista (o painel de alertas não é do perfil dele). Falha no envio nunca muda a resposta da
telemetria (fica só no log, sem endereço nem chaves); o serviço de push respondendo `404` ou
`410` (inscrição expirada) faz a API apagar a inscrição.

Configuração (app settings da Function App): `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` (só no app
setting, nunca no repositório) e `VAPID_SUBJECT` (contato `https://` ou `mailto:`).

## Chat do site

### `POST /chat`

Acesso: aberto. Responde perguntas sobre o ColdTrack com um modelo de linguagem do Azure
OpenAI (`gpt-4.1-mini`), usando como contexto os trechos da documentação mais parecidos com a
pergunta (base `cloud/function/base_chat.json`, busca por embeddings). O modelo só responde
sobre o projeto; fora do assunto, ou sem informação na base, diz que não sabe e indica o botão
Falar com o desenvolvedor (WhatsApp).

```json
{"pergunta": "Como a manga é classificada?",
 "historico": [{"papel": "usuario", "texto": "oi"}, {"papel": "assistente", "texto": "Olá!"}]}
```

| campo | regra |
|---|---|
| `pergunta` | obrigatória, 1 a 500 caracteres |
| `historico` | opcional; até 6 mensagens anteriores da conversa, cada uma `{"papel": "usuario" ou "assistente", "texto": até 1000 caracteres}` |

Campo não previsto é erro. Nada da conversa é gravado no servidor; o log guarda só o tamanho
da pergunta.

| resposta | corpo |
|---|---|
| `200` | `{"resposta": "...", "fontes": ["docs/api.md", "FAQ do site"], "origem": "ia"}` |
| `400` | erros de validação (ex.: `pergunta: no máximo 500 caracteres`, `historico[0].papel: use usuario ou assistente`) |
| `429` | `muitas perguntas seguidas. Tente de novo em 1 min.` (mais de 10 perguntas por minuto do mesmo IP) |
| `429` | `o chat atingiu o limite de perguntas de hoje. Tente de novo amanhã.` (2000 perguntas no dia, somando todos os IPs) |
| `503` | `chat indisponível`: IA não configurada, fora do ar, sem cota ou sem resposta em 20 s |

`fontes` lista os documentos usados como contexto, sem repetir. No `503`, o site usa as
respostas prontas do FAQ. Pergunta com erro de validação não gasta a cota do dia. Todo link
`http(s)` na resposta que não seja do site (`https://stcoldtrackweb7319.z15.web.core.windows.net`)
sai como `[link removido]`.

## Assistente do painel

### `POST /assistente`

Acesso: token (`operador` e `gestor`). Assistente do painel para o usuário logado: tira
dúvidas de uso (o que cada tela faz, como cadastrar veículo, registrar sensor, registrar
viagem, como funcionam alertas e faixas, o que gestor e operador podem fazer) e responde
sobre os dados da **própria empresa**. Não executa ações: quando pedem uma, explica o caminho
nas telas (Dashboard, Veículos, Sensores, Viagens, Alertas, Relatórios, Configurações).

Corpo e validação iguais aos de `POST /chat` (`pergunta` 1 a 500 caracteres, `historico`
opcional com até 6 mensagens de até 1000 caracteres; campo não previsto é erro).

A cada pergunta a API monta um retrato somente leitura da empresa do token, com as mesmas
consultas das rotas `GET` do painel (nunca de outra empresa), e o envia ao modelo junto com
os trechos da base do chat:

- empresa, nome e perfil de quem pergunta, data e hora atuais (horário de Pernambuco, UTC-3);
- perfis de carga e faixas; veículos (até 30: id, tipo, perfil, sensor);
- sensores (até 10, os ligados a veículo primeiro): última leitura (temperatura, umidade,
  RSSI, status, horários e "sem sinal há X" quando passa de 10 min) e resumo das últimas
  24 h (até 500 leituras: quantidade, mínima, máxima, média, leituras em atenção e em crítico,
  horário da última fora da faixa);
- viagens em andamento (até 10), agendadas (até 5) e as 5 últimas encerradas;
- só para `gestor`: usuários da empresa (e-mail, nome, perfil) e a contagem por perfil.

Os totais acompanham as listas cortadas; acima de ~18 mil caracteres as listas encolhem.

| resposta | corpo |
|---|---|
| `200` | `{"resposta": "...", "fontes": ["dados da empresa", "docs/api.md"], "origem": "ia"}` |
| `400` | erros de validação (os mesmos de `POST /chat`) |
| `401` | `faça login para continuar` |
| `429` | `muitas perguntas seguidas. Tente de novo em 1 min.` (mais de 15 perguntas por minuto do mesmo usuário) |
| `429` | `sua empresa atingiu o limite de perguntas de hoje ao assistente. Tente de novo amanhã.` (300 perguntas no dia por empresa) |
| `503` | `assistente indisponível`: IA não configurada, banco ou IA fora do ar, sem resposta em 20 s |

`fontes` começa sempre com `dados da empresa`, seguida dos documentos da base usados como
contexto. Pergunta fora do assunto recebe recusa curta e `fontes: []`. Nada da conversa é
gravado; o log guarda só o usuário (e-mail mascarado) e o tamanho da pergunta.

Os textos do retrato (nomes, tipos, cargas, cidades) foram digitados por usuários e podem
trazer instruções maliciosas. O prompt manda o modelo tratar o bloco como dado, nunca como
instrução, e não escrever links nem pedir login ou credencial; e a resposta passa pelo mesmo
filtro de links do `POST /chat`.

## Motorista

### `GET /motorista`

Acesso: só `motorista` (operador e gestor recebem `403`). Somente leitura. Alimenta a tela do
motorista no celular e devolve **apenas o veículo vinculado à conta**: o veículo vem do cadastro
do usuário, relido do banco a cada chamada, nunca da URL.

```json
{
  "veiculo": {"id": "CT-001", "tipo": "Caminhão baú refrigerado", "perfil": "manga"},
  "faixa": {"nome": "Manga", "min": 10.0, "max": 13.0, "margem": 3.0},
  "leitura": {"temperatura": 11.8, "umidade": 87.0, "status": "NORMAL",
              "medidoEm": "2026-11-10T21:30:00+00:00"},
  "status": "NORMAL",
  "minutosSemLeitura": 1,
  "viagem": {"origem": "Petrolina - PE", "destino": "Suape - PE",
             "carga": "Manga Tommy, 12 paletes", "inicio": "2026-11-10T06:00:00-03:00", "fim": null},
  "historico": [{"temperatura": 11.6, "status": "NORMAL", "medidoEm": "2026-11-10T20:31:00+00:00"},
                {"temperatura": 11.8, "status": "NORMAL", "medidoEm": "2026-11-10T21:30:00+00:00"}],
  "sensor": "ok",
  "sensorFalhaDesde": null
}
```

- `leitura`: a mais nova do sensor do veículo, ou `null` se ele nunca enviou (ou o veículo está
  sem sensor). `leitura.status` é a classificação gravada com ela.
- `status`: `NORMAL`, `ATENCAO`, `CRITICO` (os mesmos da telemetria) ou `SEM_LEITURA`, quando
  não há leitura ou a última foi medida há mais de 5 min (o sensor envia a cada 20 s). Sem
  sinal, `leitura` continua com o último valor, para a tela mostrá-lo como antigo.
- `minutosSemLeitura`: minutos inteiros desde a medição da última leitura; `null` sem leitura.
- `viagem`: a viagem do veículo em curso (começou e não tem fim, ou o fim ainda não chegou); com
  mais de uma, a que começou por último. `null` quando não há.
- `historico`: leituras da última hora, da mais antiga para a mais nova (no máximo 180), só com
  `temperatura`, `status` e `medidoEm`. Alimenta o mini gráfico e a lista de alertas da tela.
  Lista vazia quando o veículo não tem sensor ou não houve leitura na última hora.
- `sensor` e `sensorFalhaDesde`: estado do sensor de temperatura, com a mesma regra de
  `GET /dispositivos` (`falha` quando o contato mais recente foi um heartbeat `sensor_falha`).
  `null` quando o veículo não tem sensor ou o sensor nunca falou.

Erros: `401`; `403` para outro perfil; `404` `nenhum veículo vinculado a este motorista; fale com o
gestor` (o veículo saiu da frota); `429` `muitas consultas seguidas. Tente de novo em 1 min.`

## Leituras

### `GET /leituras?deviceId=<id>&limite=50&horas=24&status=ATENCAO,CRITICO`

Acesso: operador, gestor.

| parâmetro | regra |
|---|---|
| `deviceId` | obrigatório; sensor da empresa do usuário |
| `limite` | inteiro, padrão 50, ajustado para 1 a 500 |
| `horas` | opcional; inteiro de 1 a 168 (medidas nas últimas N horas) |
| `status` | opcional; `NORMAL`, `ATENCAO`, `CRITICO` separados por vírgula |

Resposta `200`, da medição mais recente para a mais antiga:

```json
{"deviceId": "coldtrack-01",
 "leituras": [{"deviceId", "temperatura", "umidade", "rssi", "perfil", "status", "medidoEm", "recebidoEm"}]}
```

`medidoEm` e `recebidoEm` em ISO 8601 UTC. Erros: `400` (`informe ?deviceId=`,
`limite deve ser inteiro`, filtros inválidos); `404` `dispositivo não encontrado`.

## Risco térmico (modelo)

### `GET /predict?mes=<1..12>&hora=<0..23>`

Acesso: operador, gestor.

Chance de a temperatura **externa** passar de 30 °C no mês e na hora da saída. O modelo é a
tabela 12 × 24 de `cloud/function/modelo_risco.json`, gerada por
[`analise/exportar_modelo.py`](../analise/exportar_modelo.py) com os dados horários da estação
INMET A307 (Petrolina): treino 2019–2022, teste 2023–2025. A Function só consulta a célula
pedida (sem pandas nem scikit-learn no pacote). Ficha do modelo:
[`model-card.md`](model-card.md).

| parâmetro | regra |
|---|---|
| `mes` | obrigatório; inteiro de 1 a 12 |
| `hora` | obrigatório; inteiro de 0 a 23, horário de Brasília |

Resposta `200`:

```json
{"mes": 10, "hora": 15, "limiarC": 30.0,
 "probabilidade": 0.9839, "nivel": "alto", "horasDeHistorico": 62,
 "baseline": {"probabilidade": 0.2143, "nivel": "moderado"},
 "modelo": {"versao": "clima-a307-30c-v1", "fonte": "INMET, estação automática A307 (Petrolina), dados horários",
            "anosTreino": [2019, 2020, 2021, 2022], "anosTeste": [2023, 2024, 2025],
            "brierModelo": 0.0911, "brierBaseline": 0.2017, "usaLeiturasDoSensor": false}}
```

- `nivel`: `baixo` até 0,20; `moderado` até 0,50; `alto` acima de 0,50 (o mesmo corte de 50%
  usado na avaliação).
- `baseline`: modelo ingênuo para comparação, a fração de horas acima de 30 °C nos anos de
  treino, igual para qualquer mês e hora.
- `horasDeHistorico`: horas de treino que sustentam a célula (tamanho da amostra).
- `usaLeiturasDoSensor` é sempre `false`: o modelo usa a estação pública, não as leituras do
  sensor do baú.

Erros: `400` (`mes: inteiro de 1 a 12`, `hora: inteiro de 0 a 23`); `401` sem token;
`503` `modelo indisponível` (arquivo do modelo ausente no pacote publicado).

Atualizar o modelo: `cd analise && python exportar_modelo.py` (precisa de
`dados/inmet_rota_horario.csv`, ver [`analise/README.md`](../analise/README.md)) e publicar a
API com o novo `modelo_risco.json`.

### `GET /predict/sensor?deviceId=<id>`

Acesso: operador e gestor (com `deviceId` de um sensor da empresa do token); motorista (sempre o
sensor do veículo vinculado a ele, `deviceId` ignorado).

Temperatura do sensor prevista **10 min à frente** da última leitura, a partir das leituras dos
últimos 20 min do próprio sensor. Modelo: regressão ridge de
[`analise/sensor/modelo_previsao.py`](../analise/sensor/modelo_previsao.py), exportada em
`cloud/function/modelo_sensor.json`; baseline: persistência (última leitura). Ficha do modelo:
[`model-card.md`](model-card.md).

Resposta `200`:

```json
{"deviceId": "coldtrack-01", "horizonteMin": 10,
 "ultimaLeitura": {"medidoEm": "2026-11-17T06:17:05+00:00", "perfil": "demonstrativo", "temperatura": 32.8, "status": "CRITICO"},
 "previsao": {"para": "2026-11-17T06:27:05+00:00", "temperatura": 32.8, "status": "CRITICO"},
 "baseline": {"para": "2026-11-17T06:27:05+00:00", "temperatura": 32.8, "status": "CRITICO"},
 "recomendada": "baseline", "antecipaExcursao": false, "motivo": null,
 "modelo": {"versao": "sensor-ridge-10min-v3", "fonte": "Cosmos DB de produção, leituras da placa (...)",
            "treino": {"de", "ate", "amostras"}, "teste": {"de", "ate", "amostras"},
            "maeModelo": 0.3828, "maeBaseline": 0.3643, "rmseModelo": 0.7421, "rmseBaseline": 0.723,
            "superaBaseline": false, "usaLeiturasDoSensor": true}}
```

- `previsao`: valor do modelo; `baseline`: última leitura repetida. O `status` de cada uma é a
  classificação no perfil de carga da última leitura.
- `recomendada`: `modelo` ou `baseline`, a que teve menor MAE no teste temporal. É a que a tela
  deve mostrar. Hoje é `baseline` (o modelo não superou a persistência).
- `antecipaExcursao`: `true` quando a previsão recomendada cai num status pior que o da última
  leitura.
- `motivo`: `null`, ou `sem_leituras` (nada nos últimos 20 min), `sem_leitura_recente` (última
  leitura há mais de 5 min; `previsao` e `baseline` saem `null`) ou `historico_insuficiente`
  (menos de 10 min contínuos; só `previsao` sai `null`).

Erros: `400` `informe ?deviceId=` (operador ou gestor sem o parâmetro); `401` sem token; `404`
`dispositivo não encontrado` (sensor inexistente ou de outra empresa) ou `nenhum sensor
vinculado a este motorista; fale com o gestor`; `429` mais de 30 chamadas por minuto do mesmo
usuário; `503` `modelo indisponível`.

Atualizar o modelo: exportar o banco (`infra/backup/exportar.py`), rodar `python
descrever_cosmos.py --converter <export>/leituras.jsonl` e `python modelo_previsao.py` em `analise/sensor`, e
publicar a API com o novo `modelo_sensor.json`.

## Sensores (`/dispositivos`)

| método e rota | acesso | corpo | resposta |
|---|---|---|---|
| `GET /dispositivos` | operador, gestor | — | `200 {"dispositivos": [{"id", "descricao", "criadoEm", "ultimoContato", "online", "sensor", "sensorFalhaDesde"}]}` |
| `POST /dispositivos` | gestor | `{"id", "descricao"}` | `201 {"id", "descricao", "criadoEm", "chave"}` |
| `PUT /dispositivos/{id}` | gestor | — | `200 {"id", "chave"}`: gera chave nova, a anterior para de valer |
| `DELETE /dispositivos/{id}` | gestor | — | `204` |

- `id`: 3 a 40 caracteres, letras, números, `_` ou `-` (gravado em minúsculas);
  `descricao`: opcional, até 60.
- `ultimoContato`: quando chegou o contato mais recente da placa, leitura ou heartbeat (o que for
  mais novo); `null` se ela nunca enviou nada. `online`: contato há no máximo 120 s.
- `sensor`: último estado conhecido do sensor de temperatura: `falha` quando o contato mais
  recente foi um heartbeat `sensor_falha` (nenhuma leitura válida depois dele), `ok` quando foi
  uma leitura válida, `null` quando a placa nunca falou. `sensorFalhaDesde`: início da falha
  atual, `null` fora de falha. Lidos juntos: `online` com `falha` é placa viva com sensor em
  falha; `online` falso é placa sem contato (desligada ou sem rede).
- A `chave` aparece só na resposta do `POST` e do `PUT`; o banco guarda apenas o SHA-256.
- Erros: `409` `o ID ... já está em uso; escolha outro`; `404` `dispositivo não encontrado`;
  `409` no `DELETE` quando um veículo usa o sensor.

## Veículos (`/veiculos`)

| método e rota | acesso | corpo | resposta |
|---|---|---|---|
| `GET /veiculos` | operador, gestor | — | `200 {"veiculos": [veículo]}` |
| `POST /veiculos` | gestor | veículo | `201` veículo |
| `PUT /veiculos/{id}` | gestor | veículo | `200` veículo |
| `DELETE /veiculos/{id}` | gestor | — | `204` |

Veículo: `{"id", "tipo", "deviceId", "dispositivo", "perfil"}`.

| campo | regra |
|---|---|
| `id` | código de 3 a 20 caracteres, letras maiúsculas, números ou hífen (ex.: `CT-001`; convertido para maiúsculas) |
| `tipo` | obrigatório, até 60 |
| `deviceId` | sensor registrado na empresa e não usado por outro veículo |
| `dispositivo` | opcional, até 60 (descrição livre) |
| `perfil` | `demonstrativo` (padrão), `manga` ou `uva` |

Erros: `400` validação (inclusive `deviceId: o sensor ... não está registrado em Sensores` e
`deviceId: o sensor já está no veículo ...`), `400` `informe o id na rota` (PUT/DELETE sem
id), `404` `não encontrado`, `409` `já existe um cadastro com id ...`.

## Viagens (`/viagens`)

| método e rota | acesso | corpo | resposta |
|---|---|---|---|
| `GET /viagens` | operador, gestor | — | `200 {"viagens": [viagem]}` |
| `POST /viagens` | gestor | viagem | `201` viagem (id gerado: `V-` + 6 caracteres) |
| `PUT /viagens/{id}` | gestor | viagem | `200` viagem |
| `DELETE /viagens/{id}` | gestor | — | `204` |

Viagem: `{"id", "veiculo", "origem", "destino", "carga", "inicio", "fim"}`.

| campo | regra |
|---|---|
| `veiculo` | código de veículo cadastrado na empresa (até 20) |
| `origem`, `destino` | obrigatórios, até 80 |
| `carga` | obrigatório, até 120 |
| `inicio` | ISO 8601 com fuso horário |
| `fim` | opcional; ISO 8601 com fuso, depois de `inicio` |

Erros: os mesmos de veículos, mais `veiculo: ... não está cadastrado`.

## Usuários (`/usuarios`)

Todas as operações exigem perfil gestor e valem só para a empresa dele.

| método e rota | corpo | resposta |
|---|---|---|
| `GET /usuarios` | — | `200 {"usuarios": [{"id", "nome", "perfil", "veiculo"?}]}` |
| `POST /usuarios` | `{"email", "nome", "perfil", "senha", "veiculo"?}` | `201 {"id", "nome", "perfil", "empresaId", "veiculo"?}` |
| `PUT /usuarios/{email}` | `{"senha"}` e/ou `{"veiculo"}` | `200 {"id", "nome", "perfil", "empresaId", "veiculo"?}`: com `senha`, redefine a senha de outro usuário, derruba as sessões dele e tira a conta da espera do login; com `veiculo`, troca o veículo de um motorista (sem mexer na senha nem nas sessões) |
| `DELETE /usuarios/{email}` | — | `204` |

Regras do `POST` iguais às de `POST /empresas` (sem `empresa`), com `perfil` `operador`,
`gestor` ou `motorista`. `veiculo` é obrigatório no perfil `motorista` e proibido nos outros, e
precisa ser um veículo da frota da empresa (de outra empresa responde igual a inexistente):
`veiculo: obrigatório para o perfil motorista`, `veiculo: só o perfil motorista tem veículo
vinculado`, `veiculo: CT-999 não está cadastrado na frota`. Erros: `400` validação, `você não pode remover o próprio usuário` ou, no `PUT`
com o próprio e-mail, `para trocar a própria senha use Configurações → Trocar senha` (a
própria senha só muda com a atual, em `POST /senha`); `404`
`não encontrado`; `409` `já existe um usuário com esse e-mail`.
