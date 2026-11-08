# API do ColdTrack

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
| chave do sensor | header `x-device-key: <chave>` | `POST /telemetria` |
| token do painel | header `Authorization: Bearer <token>` | rotas do painel, `POST /assistente` e `POST /sair` |
| nenhuma | — | `POST /empresas`, `POST /login`, `GET /perfis`, `POST /chat` |

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
| `POST /chat` | 10 perguntas por minuto por IP; 2000 por dia no site todo | `429` |
| `POST /assistente` | 15 perguntas por minuto por usuário; 300 por dia por empresa | `429` |

As janelas são fixas (o minuto, os 15 min ou o dia corrente, em UTC).

### Códigos comuns

| código | quando | mensagem |
|---|---|---|
| `400` | corpo não é JSON | `corpo não é JSON válido` |
| `400` | corpo não é objeto | `corpo deve ser um objeto JSON` |
| `401` | sem token, token inválido/expirado ou sessão derrubada | `faça login para continuar` |
| `403` | perfil sem permissão | `seu perfil não tem acesso a esta ação` |
| `404` | item inexistente ou de outra empresa (as duas respondem igual) | `não encontrado` / `dispositivo não encontrado` |

Perfis: `operador` (consulta) e `gestor` (consulta e cadastra).

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
`400` validação; `409` `já existe uma conta com esse e-mail`. O id da empresa é gerado
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

Acesso: operador, gestor. Resposta `200`: `{"id", "nome", "perfil", "empresaId", "empresa"}`.

### `POST /senha`

Acesso: operador, gestor. Troca a própria senha.

```json
{"atual": "********", "nova": "********"}
```

`nova` com 8 a 128 caracteres e diferente de `atual`. Respostas: `200 {"token", "usuario"}`
(novo token; os anteriores param de valer); `400` validação ou `atual: senha atual incorreta`.

### `POST /sair`

Acesso: operador, gestor. Sem corpo. Encerra **todas** as sessões do usuário (todos os
aparelhos): sobe a versão da sessão e todo token já emitido passa a receber `401`.
Resposta: `204`. O painel deve chamar antes de apagar o token guardado no navegador.

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

## Sensores (`/dispositivos`)

| método e rota | acesso | corpo | resposta |
|---|---|---|---|
| `GET /dispositivos` | operador, gestor | — | `200 {"dispositivos": [{"id", "descricao", "criadoEm"}]}` |
| `POST /dispositivos` | gestor | `{"id", "descricao"}` | `201 {"id", "descricao", "criadoEm", "chave"}` |
| `PUT /dispositivos/{id}` | gestor | — | `200 {"id", "chave"}`: gera chave nova, a anterior para de valer |
| `DELETE /dispositivos/{id}` | gestor | — | `204` |

- `id`: 3 a 40 caracteres, letras, números, `_` ou `-` (gravado em minúsculas);
  `descricao`: opcional, até 60.
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
| `GET /usuarios` | — | `200 {"usuarios": [{"id", "nome", "perfil"}]}` |
| `POST /usuarios` | `{"email", "nome", "perfil", "senha"}` | `201 {"id", "nome", "perfil", "empresaId"}` |
| `PUT /usuarios/{email}` | `{"senha"}` | `200 {"id", "nome", "perfil", "empresaId"}`: redefine a senha de outro usuário, derruba as sessões dele e tira a conta da espera do login |
| `DELETE /usuarios/{email}` | — | `204` |

Regras do `POST` iguais às de `POST /empresas` (sem `empresa`), com `perfil` `operador` ou
`gestor`. Erros: `400` validação, `você não pode remover o próprio usuário` ou, no `PUT`
com o próprio e-mail, `para trocar a própria senha use Configurações → Trocar senha` (a
própria senha só muda com a atual, em `POST /senha`); `404`
`não encontrado`; `409` `já existe um usuário com esse e-mail`.
