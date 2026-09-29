# Azure Function — ColdTrack Edge

API do ColdTrack: recebe a telemetria dos sensores, valida o contrato JSON, classifica a leitura
pela faixa da carga, grava no Azure Cosmos DB e atende o painel (login, cadastros, consultas).
Cada empresa só enxerga os próprios dados.

Visão completa (modelo de dados, segurança, publicação): [`docs/stack-tecnica.md`](../../docs/stack-tecnica.md).

## Recursos no Azure (região Brazil South, resource group `rg-coldtrack`)

| recurso | nome |
|---|---|
| Function App (Flex Consumption, Python 3.11) | `func-coldtrack-7319` |
| Cosmos DB for NoSQL (free tier) | `cosmos-coldtrack-7319` — banco `coldtrack`: `empresas`, `usuarios`, `dispositivos`, `veiculos`, `viagens` (partição `/id`) e `leituras` (partição `/deviceId`) |
| Storage Account | `stcoldtrack7319` |

App settings: `COSMOS_CONNECTION` e `JWT_SECRET`.

## Endpoints

Base: `https://func-coldtrack-7319.azurewebsites.net/api`

| rota | quem | acesso |
|---|---|---|
| `POST /telemetria` | sensor | chave própria do sensor no header `x-device-key` |
| `POST /empresas` | pessoa | aberta: cria a empresa e o primeiro gestor |
| `POST /login` | pessoa | e-mail e senha → token (8 h) |
| `GET /perfis` | painel | aberta |
| `GET /eu`, `POST /senha` | operador, gestor | `Authorization: Bearer <token>` |
| `GET /leituras`, `GET /dispositivos`, `GET /veiculos`, `GET /viagens` | operador, gestor | token |
| `POST /dispositivos`, `PUT/DELETE /dispositivos/{id}` | gestor | token |
| `POST /veiculos`, `PUT/DELETE /veiculos/{id}` | gestor | token |
| `POST /viagens`, `PUT/DELETE /viagens/{id}` | gestor | token |
| `GET/POST /usuarios`, `PUT/DELETE /usuarios/{id}` | gestor | token |

Sem token ou sessão derrubada: 401. Perfil sem permissão: 403. Dado de outra empresa: 404.
Login bloqueado: 429. O acesso é conferido pela API em cada chamada; a tela só esconde o que o
perfil não pode fazer.

### Acesso

- Senhas com scrypt e sal por usuário; o hash nunca sai da API.
- Token JWT HS256 com a empresa e a versão da sessão. Trocar ou redefinir a senha, ou remover
  o usuário, derruba os tokens antigos na hora (a API confere o usuário no banco a cada chamada).
- Mesma mensagem e mesmo tempo para e-mail inexistente e senha errada; 5 senhas erradas
  seguidas bloqueiam a conta por 15 minutos (o gestor libera redefinindo a senha).
- Chave de sensor: 32 bytes aleatórios, mostrada uma vez no registro; o banco guarda o SHA-256.

### `POST /telemetria`

```
x-device-key: <chave do sensor>

{"deviceId": "coldtrack-01", "temperatura": 12.4, "umidade": 81.0, "rssi": -58, "medidoEm": 1790000000}
```

`rssi` pode ser `null` quando o rádio devolve valor impossível (o simulador Wokwi reporta RSSI positivo); `temperatura` e `umidade` nunca.
`medidoEm` (opcional) é o horário da medição em epoch UTC; leituras guardadas sem conexão chegam depois com o horário original.

| resposta | quando |
|---|---|
| `201 {"id", "status", "perfil", "faixa": {"min", "max", "margem"}}` | leitura válida gravada; o sensor usa a faixa nos LEDs |
| `400 {"erros": [...]}` | JSON inválido, campo faltando, texto no lugar de número, NaN, valor fora da faixa física, horário inválido, campo não previsto |
| `401` | sensor não registrado, chave errada ou chave de outro sensor |

Classificação pelo perfil de carga do veículo que usa o sensor (`contrato.py`, `PERFIS_CARGA`):
faixa normal `[min, max]`; até `margem` °C fora é `ATENCAO`; além disso, `CRITICO`.
Sensor sem veículo usa o perfil demonstrativo (normal até 15 °C, atenção até 20 °C).

### `GET /leituras?deviceId=coldtrack-01&limite=50&horas=24&status=ATENCAO,CRITICO`

Leituras de um sensor da empresa, da medição mais recente para a mais antiga. `limite` de 1 a
500; `horas` (1 a 168) e `status` são opcionais.

## Testes

```bash
cd cloud/function
python -m unittest -v
```

## Deploy

Automático pelo GitHub Actions (`publicar-api.yml`) a cada push na branch `everson` que altere
esta pasta. Manual: `bash publicar.sh`.

## Scripts de suporte

| script | uso |
|---|---|
| `criar_usuario.py` | cria um usuário direto no banco numa empresa existente |
| `migrar_multiempresa.py` | migração única dos dados do piloto para o modelo com empresas (já executada em 26/09/2026) |
