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
| token do painel | header `Authorization: Bearer <token>` | rotas do painel |
| nenhuma | — | `POST /empresas`, `POST /login`, `GET /perfis` |

O token é um JWT HS256 válido por 8 horas, emitido por `POST /login`, `POST /empresas` e
`POST /senha`. A cada chamada a API confere o usuário no banco: usuário removido, senha
trocada ou redefinida (versão da sessão diferente) e empresa diferente derrubam o token.
O perfil considerado é o atual do usuário, não o de quando o token foi emitido.

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
| `401` | `e-mail ou senha incorretos` (mesma mensagem e mesmo tempo para e-mail inexistente) |
| `429` | `muitas tentativas erradas. Tente de novo em N min.` (5 erros seguidos bloqueiam por 15 min) |

### `GET /eu`

Acesso: operador, gestor. Resposta `200`: `{"id", "nome", "perfil", "empresaId", "empresa"}`.

### `POST /senha`

Acesso: operador, gestor. Troca a própria senha.

```json
{"atual": "********", "nova": "********"}
```

`nova` com 8 a 128 caracteres e diferente de `atual`. Respostas: `200 {"token", "usuario"}`
(novo token; os anteriores param de valer); `400` validação ou `atual: senha atual incorreta`.

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
| `PUT /usuarios/{email}` | `{"senha"}` | `200 {"id", "nome", "perfil", "empresaId"}`: redefine a senha, derruba as sessões e desbloqueia a conta |
| `DELETE /usuarios/{email}` | — | `204` |

Regras do `POST` iguais às de `POST /empresas` (sem `empresa`), com `perfil` `operador` ou
`gestor`. Erros: `400` validação ou `você não pode remover o próprio usuário`; `404`
`não encontrado`; `409` `já existe um usuário com esse e-mail`.
