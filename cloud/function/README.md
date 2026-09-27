# Azure Function — ColdTrack Edge

Recebe a telemetria do ESP32, valida o contrato JSON, classifica a leitura e grava no Azure Cosmos DB.

## Recursos no Azure (região Brazil South, resource group `rg-coldtrack`)

| recurso | nome |
|---|---|
| Function App (Flex Consumption, Python 3.11) | `func-coldtrack-7319` |
| Cosmos DB for NoSQL (free tier) | `cosmos-coldtrack-7319` — banco `coldtrack`: `leituras` (partição `/deviceId`), `usuarios`, `veiculos`, `viagens` (partição `/id`) |
| Storage Account | `stcoldtrack7319` |

## Endpoints

Base: `https://func-coldtrack-7319.azurewebsites.net/api`

| rota | quem | acesso |
|---|---|---|
| `POST /telemetria` | dispositivo | chave da função no header `x-functions-key` |
| `POST /login` | pessoa | e-mail e senha → token (8 h) |
| `GET /eu` | operador, gestor | `Authorization: Bearer <token>` |
| `GET /leituras` | operador, gestor | token |
| `GET /veiculos`, `GET /viagens` | operador, gestor | token |
| `POST /veiculos`, `PUT/DELETE /veiculos/{id}` | gestor | token |
| `POST /viagens`, `PUT/DELETE /viagens/{id}` | gestor | token |
| `GET/POST /usuarios`, `DELETE /usuarios/{id}` | gestor | token |

Sem token: HTTP 401. Perfil sem permissão: HTTP 403. O acesso é conferido pela API em
cada chamada; a tela só esconde o que o perfil não pode fazer.

### Login e perfis

- Senhas guardadas com scrypt e sal por usuário (`seguranca.py`); o hash nunca sai da API.
- Token JWT HS256 assinado com a app setting `JWT_SECRET` (fora do código).
- Mensagem de erro de login igual para e-mail inexistente e senha errada.
- Não há cadastro aberto. O primeiro gestor é criado localmente:

```bash
set COSMOS_CONNECTION=<string de conexão do Cosmos>
python criar_usuario.py gestor@empresa.com "Nome do Gestor" gestor
```

Os demais usuários são criados pelo gestor em **Configurações → Usuários** no painel.

### `POST /telemetria`

```json
{"deviceId": "coldtrack-01", "temperatura": 12.4, "umidade": 81.0, "rssi": -58, "medidoEm": 1790000000}
```

`rssi` pode ser `null` quando o rádio devolve valor impossível (o simulador Wokwi reporta RSSI positivo); `temperatura` e `umidade` nunca.
`medidoEm` (opcional) é o horário da medição em epoch UTC; leituras guardadas sem conexão chegam depois com o horário original.

| resposta | quando |
|---|---|
| `201 {"id": "...", "status": "NORMAL"}` | leitura válida gravada |
| `400 {"erros": [...]}` | JSON inválido, campo faltando, texto no lugar de número, NaN, valor fora da faixa física, horário inválido, campo não previsto |

Classificação (configurável pelas app settings `TEMP_NORMAL_MAX` e `TEMP_ATENCAO_MAX`):
até 15 °C `NORMAL`, até 20 °C `ATENCAO`, acima `CRITICO` — os mesmos limites do firmware.

### `GET /leituras?deviceId=coldtrack-01&limite=50&horas=24&status=ATENCAO,CRITICO`

Leituras do dispositivo, da medição mais recente para a mais antiga. `limite` de 1 a 500;
`horas` (1 a 168) e `status` são opcionais.

## Testes do contrato

```bash
cd cloud/function
python -m unittest -v
```

## Deploy

```bash
az functionapp deployment source config-zip -g rg-coldtrack -n func-coldtrack-7319 --src func.zip --build-remote true
```

O zip contém `function_app.py`, `contrato.py`, `seguranca.py`, `cadastros.py`, `host.json` e `requirements.txt`.
A string de conexão do Cosmos fica na app setting `COSMOS_CONNECTION` — nunca no código.
