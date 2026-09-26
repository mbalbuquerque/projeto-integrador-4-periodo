# Azure Function — ColdTrack Edge

Recebe a telemetria do ESP32, valida o contrato JSON, classifica a leitura e grava no Azure Cosmos DB.

## Recursos no Azure (região Brazil South, resource group `rg-coldtrack`)

| recurso | nome |
|---|---|
| Function App (Flex Consumption, Python 3.11) | `func-coldtrack-7319` |
| Cosmos DB for NoSQL (free tier) | `cosmos-coldtrack-7319` — banco `coldtrack`, container `leituras`, partição `/deviceId` |
| Storage Account | `stcoldtrack7319` |

## Endpoints

Base: `https://func-coldtrack-7319.azurewebsites.net/api`
Todas as rotas exigem a chave da função no header `x-functions-key` (sem chave: HTTP 401).

### `POST /telemetria`

```json
{"deviceId": "coldtrack-01", "temperatura": 12.4, "umidade": 81.0, "rssi": -58}
```

`rssi` pode ser `null` quando o rádio devolve valor impossível (o simulador Wokwi reporta RSSI positivo); `temperatura` e `umidade` nunca.

| resposta | quando |
|---|---|
| `201 {"id": "...", "status": "NORMAL"}` | leitura válida gravada |
| `400 {"erros": [...]}` | JSON inválido, campo faltando, texto no lugar de número, NaN, valor fora da faixa física, campo não previsto |

Classificação (configurável pelas app settings `TEMP_NORMAL_MAX` e `TEMP_ATENCAO_MAX`):
até 15 °C `NORMAL`, até 20 °C `ATENCAO`, acima `CRITICO` — os mesmos limites do firmware.

### `GET /leituras?deviceId=coldtrack-01&limite=50`

Últimas leituras do dispositivo, da mais recente para a mais antiga (`limite` entre 1 e 500).

## Testes do contrato

```bash
cd cloud/function
python -m unittest -v
```

## Deploy

```bash
az functionapp deployment source config-zip -g rg-coldtrack -n func-coldtrack-7319 --src func.zip --build-remote true
```

O zip contém `function_app.py`, `contrato.py`, `host.json` e `requirements.txt`.
A string de conexão do Cosmos fica na app setting `COSMOS_CONNECTION` — nunca no código.
