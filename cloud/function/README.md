# Azure Function — ColdTrack Edge

API do ColdTrack: recebe a telemetria dos sensores, valida o contrato JSON, classifica a leitura
pela faixa da carga, grava no Azure Cosmos DB e atende o painel (login, cadastros, consultas).
Cada empresa só enxerga os próprios dados.

Visão completa (modelo de dados, segurança, publicação): [`docs/stack-tecnica.md`](../../docs/stack-tecnica.md).
Referência de todas as rotas: [`docs/api.md`](../../docs/api.md). Infraestrutura em Bicep:
[`infra/`](../../infra/README.md).

## Recursos no Azure (região Brazil South, resource group `rg-coldtrack`)

| recurso | nome |
|---|---|
| Function App (Flex Consumption, Python 3.11) | `func-coldtrack-7319` |
| Cosmos DB for NoSQL (free tier) | `cosmos-coldtrack-7319` — banco `coldtrack`: `empresas`, `usuarios`, `dispositivos`, `veiculos`, `viagens` (partição `/id`) e `leituras` (partição `/deviceId`) |
| Storage Account | `stcoldtrack7319` |
| Azure OpenAI | `aoai-coldtrack-7319` — deploys `gpt-4.1-mini` (resposta do chat) e `text-embedding-3-small` (busca na base) |

App settings lidas pelo código: `COSMOS_CONNECTION`, `COSMOS_DATABASE`, `COSMOS_CONTAINER`,
`JWT_SECRET` e, para o chat, `AOAI_ENDPOINT`, `AOAI_DEPLOY_CHAT`, `AOAI_DEPLOY_EMBED` e
`AOAI_API_VERSION` (lista completa em [`infra/README.md`](../../infra/README.md)). O chat entra
no Azure OpenAI pela identidade gerenciada da Function, sem chave guardada.

## Endpoints

Base: `https://func-coldtrack-7319.azurewebsites.net/api`

| rota | quem | acesso |
|---|---|---|
| `POST /telemetria` | sensor | chave própria do sensor no header `x-device-key` |
| `POST /empresas` | pessoa | aberta: cria a empresa e o primeiro gestor |
| `POST /login` | pessoa | e-mail e senha → token (8 h) |
| `GET /perfis` | painel | aberta |
| `POST /chat` | site | aberta: pergunta ao assistente (10 por minuto por IP, 2000 por dia no total) |
| `GET /eu`, `POST /senha`, `POST /sair` | operador, gestor | `Authorization: Bearer <token>` |
| `POST /assistente` | operador, gestor | token: assistente do painel (15 por minuto por usuário, 300 por dia por empresa) |
| `GET /leituras`, `GET /dispositivos`, `GET /veiculos`, `GET /viagens` | operador, gestor | token |
| `POST /dispositivos`, `PUT/DELETE /dispositivos/{id}` | gestor | token |
| `POST /veiculos`, `PUT/DELETE /veiculos/{id}` | gestor | token |
| `POST /viagens`, `PUT/DELETE /viagens/{id}` | gestor | token |
| `GET/POST /usuarios`, `PUT/DELETE /usuarios/{id}` | gestor | token |

Sem token ou sessão derrubada: 401. Perfil sem permissão: 403. Dado de outra empresa: 404.
Muitas falhas de login do mesmo IP: 429. O acesso é conferido pela API em cada chamada; a tela só esconde o que o
perfil não pode fazer.

### Acesso

- Senhas com scrypt e sal por usuário; o hash nunca sai da API.
- Token JWT HS256 com a empresa e a versão da sessão. Trocar ou redefinir a senha, sair
  (`POST /sair`) ou remover o usuário derruba os tokens antigos na hora (a API confere o
  usuário no banco a cada chamada).
- Mesma resposta (401) e mesmo tempo para e-mail inexistente, senha errada e conta em espera.
  A partir da 5ª senha errada seguida a conta espera 1 min, dobrando até 15 min (o gestor
  libera redefinindo a senha); cada IP tem até 20 falhas a cada 15 min.
- Limites de uso contados no container `limites` do Cosmos, somando todas as instâncias
  (`limites.py`). Detalhes e limitações conhecidas: [`docs/seguranca.md`](../../docs/seguranca.md).
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

### `POST /chat`

Assistente do site com um modelo de linguagem do Azure OpenAI (`chat.py`). A pergunta vira um
embedding, os 4 trechos mais parecidos de `base_chat.json` (cosseno em Python puro) entram no
prompt como contexto e o modelo responde em português, só sobre o ColdTrack. Sem
configuração ou com falha da IA, responde `503` e o site cai no FAQ. Detalhes em
[`docs/api.md`](../../docs/api.md).

### `POST /assistente`

Assistente do painel (`assistente.py`), para o usuário logado. Monta um retrato somente leitura
da empresa do token (veículos, sensores com última leitura e resumo de 24 h, viagens e, para
gestor, usuários) com as mesmas consultas das rotas `GET`, junta os trechos da base do chat e
responde sobre o uso do painel e os dados da empresa. Não executa ações. Detalhes em
[`docs/api.md`](../../docs/api.md).

### `GET /leituras?deviceId=coldtrack-01&limite=50&horas=24&status=ATENCAO,CRITICO`

Leituras de um sensor da empresa, da medição mais recente para a mais antiga. `limite` de 1 a
500; `horas` (1 a 168) e `status` são opcionais.

## Rodar localmente

Requer Python 3.11 e o [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local) v4.

```bash
cd cloud/function
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp local.settings.example.json local.settings.json  # preencher COSMOS_CONNECTION e JWT_SECRET
func start                                          # http://localhost:7071/api
```

O `local.settings.json` está no `.gitignore`. Usar um banco de desenvolvimento, nunca o de
produção. Para o chat local, a conta do `az login` precisa do papel "Cognitive Services OpenAI
User" no recurso do Azure OpenAI: a autenticação por chave está desligada no recurso
(`AOAI_KEY` só serve para outro recurso que aceite chave).

### Base de conhecimento do chat

```bash
cd cloud/function
export AOAI_ENDPOINT=https://aoai-coldtrack-7319.openai.azure.com/
export AOAI_DEPLOY_EMBED=text-embedding-3-small
python scripts/gerar_base_chat.py --seco                         # só lista os trechos
python scripts/gerar_base_chat.py --front ../../../Front-End-pi  # gera e grava base_chat.json
python -m unittest
```

Só entram os arquivos listados no script (READMEs, `docs/` e o FAQ do painel); `.specs`,
`local.settings*`, `secrets.h` e `.txt` nunca são lidos, e trecho com cara de credencial é
descartado. Os vetores têm 512 dimensões (`chat.DIMENSOES`), iguais na base e na pergunta.

## Testes e lint

```bash
cd cloud/function
python -m unittest -v
pip install ruff==0.17.4 && ruff check .
```

## Deploy

Automático pelo GitHub Actions (`publicar-api.yml`) a cada push na branch `everson` que altere
esta pasta. Manual: `bash publicar.sh`. Os dois publicam exatamente os arquivos listados em
`pacote.txt`; o `test_pacote.py` falha se um módulo novo da API ficar de fora. Testes,
`scripts/` e configuração de lint não são publicados.

## Scripts de suporte

Ficam em `scripts/` e rodam a partir desta pasta (ex.: `python scripts/criar_usuario.py`).

| script | uso |
|---|---|
| `scripts/criar_usuario.py` | cria um usuário direto no banco numa empresa existente |
| `scripts/gerar_base_chat.py` | gera `base_chat.json` (trechos da documentação dos dois repositórios e do FAQ do site, com embeddings); rodar de novo quando a documentação mudar |
| `scripts/migrar_multiempresa.py` | migração única dos dados do piloto para o modelo com empresas (já executada em 26/09/2026) |
