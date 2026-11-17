# ColdTrack Edge

Portuguese version: [README.md](README.md).

Cold chain monitoring for refrigerated fruit transport (mango and grape from the Sao Francisco
Valley, Brazil). A sensor node built on an ESP32-C3 measures temperature and humidity inside the
cargo compartment, classifies each reading against the cargo's range, signals the result on the
board, and sends the telemetry to an API on Azure. A web dashboard shows the readings, the alerts,
and each company's records.

Integrative Project, 4th term, Faculdade Senac PE, 2026.2.

The project has two repositories:

| repository | contents |
|---|---|
| [projeto-integrador-4-periodo](https://github.com/mbalbuquerque/projeto-integrador-4-periodo) (this one) | ESP32-C3 firmware, API (Azure Functions, Python), infrastructure, climate analysis and documentation |
| [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi) | web dashboard (React + Vite) published on Azure Storage |

Both are published from the `main` branch (see [Deployment](#deployment)).

| | address |
|---|---|
| Published dashboard | <https://stcoldtrackweb7319.z15.web.core.windows.net> |
| API (interactive documentation, Swagger) | <https://func-coldtrack-7319.azurewebsites.net/api/docs> |
| API (base) | `https://func-coldtrack-7319.azurewebsites.net/api` |
| Wokwi simulation | <https://wokwi.com/projects/475352296477619201> |
| ThingSpeak channel (physical board over MQTT) | <https://thingspeak.mathworks.com/channels/3515173> |

## Architecture

```
 ESP32-C3 + DHT11/DHT22                          Azure (rg-coldtrack, Brazil South)
 +-----------------------+    HTTPS + JSON     +--------------------------------+
 | reads every cycle     |  x-device-key       | Azure Function (Python 3.11)   |
 | classifies by range   | ------------------> | POST /api/telemetria           |
 | LEDs or OLED screen   | <------------------ | validates, classifies, stores  |
 | flash queue (offline, |  status + range     +---------------+----------------+
 | resends later)        |                                     |
 +-----------+-----------+                                     v
             |                                 +--------------------------------+
             | MQTT/TLS (optional)             | Cosmos DB for NoSQL            |
             v                                 | empresas, usuarios, veiculos,  |
       ThingSpeak                              | dispositivos, viagens, leituras|
                                               +---------------+----------------+
                                                               ^
 Browser (dashboard)         JWT token                         |
 +-----------------------+   Authorization: Bearer   +---------+----------------+
 | static site on        | ------------------------> | dashboard routes on the  |
 | Azure Storage ($web)  |                           | same Azure Function      |
 +-----------------------+                           +--------------------------+
```

The dashboard is a React + Vite application (repository [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi)).
The API is the only source of data: the dashboard does not read ThingSpeak, which appears only on
the demonstration Monitoring screen and in the firmware's optional MQTT upload. The cargo profiles
(mango, grape, demonstration) define the temperature range of each vehicle; the API sends the range
to the sensor on every reading.

The site chat (`POST /api/chat`) answers questions about the project with an Azure OpenAI language
model (`gpt-4.1-mini`), using excerpts of this documentation as context (embedding search); if the
AI does not answer, the site falls back to the FAQ. Inside the dashboard, the dashboard assistant
(`POST /api/assistente`, login required) answers questions about how to use the screens and about
the company's own data (sensors, readings, vehicles and trips), without performing actions.

Details of each layer: [`docs/stack-tecnica.md`](docs/stack-tecnica.md). API routes: [Swagger](https://func-coldtrack-7319.azurewebsites.net/api/docs) (interactive,
spec in [`cloud/function/openapi.json`](cloud/function/openapi.json)) and [`docs/api.md`](docs/api.md) (text). Azure resources: [`infra/README.md`](infra/README.md).

Note: the linked documents under `docs/`, the other READMEs and the code comments are in Portuguese. The API specification (`openapi.json`), the pitch ([`docs/pitch-en.md`](docs/pitch-en.md)), the slides and the model card ([`docs/model-card.md`](docs/model-card.md)) are in English.

## Repository structure

```
.
├── firmware/
│   ├── coldtrack/           ESP32-C3 firmware (Arduino)
│   │   ├── coldtrack.ino
│   │   ├── azure_ca.h       root certificate used for HTTPS
│   │   └── secrets.example.h  template for secrets.h (the real one is not committed to Git)
│   └── wokwi/               simulation circuit (diagram.json, libraries.txt)
├── cloud/function/          API (Azure Function in Python)
│   ├── function_app.py      routes
│   ├── contrato.py          telemetry contract, cargo profiles and classification
│   ├── seguranca.py         password, token, login wait, sensor key
│   ├── limites.py           shared usage limits (limites container)
│   ├── cadastros.py         validation of the records
│   ├── chat.py              site chat (Azure OpenAI + search in base_chat.json)
│   ├── assistente.py        dashboard assistant (company data + chat base)
│   ├── base_chat.json       documentation excerpts with embeddings, used by the chat
│   ├── test_*.py            tests (unittest)
│   ├── pacote.txt           files published to Azure
│   ├── publicar.sh          manual deployment
│   └── scripts/             support scripts (create user, migration)
├── infra/                   main.bicep of the current environment and infrastructure notes
├── analise/                 climate analysis of the route (INMET data)
├── docs/                    technical documentation, API, security, deployment, design report
└── .github/workflows/       tests (API and firmware) and API deployment
```

### Required delivery structure

The folders were not renamed to the delivery names because the path is part of the
deployment (workflows, `pacote.txt`, links in the documentation and in Wokwi). Mapping:

| required folder | where it is | contents |
|---|---|---|
| `/firmware` | [`firmware/`](firmware/) | ESP32-C3 firmware, firmware tests and the Wokwi circuit |
| `/backend` | [`cloud/function/`](cloud/function/) | API on Azure Functions (Python), tests and deployment |
| `/database` | [`infra/main.bicep`](infra/main.bicep) (Cosmos DB), [`infra/ci/preparar_banco.py`](infra/ci/preparar_banco.py), [`infra/backup/`](infra/backup/), [`cloud/function/scripts/`](cloud/function/scripts/) | database and container definition, test environment seeding, logical backup and restore, migration |
| `/frontend` | [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi) repository | web dashboard (React + Vite) |
| `/mobile` | [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi) repository | the same dashboard as a PWA installable on the phone (`public/manifest.json`, `public/sw.js`); there is no native app |
| `/ia` | [`analise/`](analise/), [`cloud/function/chat.py`](cloud/function/chat.py), [`cloud/function/assistente.py`](cloud/function/assistente.py) | climate analysis of the route (INMET data) and chat/assistant with Azure OpenAI |
| `/infra` | [`infra/`](infra/), [`.github/workflows/`](.github/workflows/) | Bicep, Dockerfile, compose, backup and test/deployment workflows |
| `/docs` | [`docs/`](docs/) | technical documentation, API, security, deployment |

## How to run

### Firmware

For the simulation, open the project on Wokwi (link above). To assemble a new project on Wokwi,
copy `firmware/coldtrack/coldtrack.ino` (as `sketch.ino`), `azure_ca.h`, a `secrets.h` made from
`secrets.example.h`, and the files in `firmware/wokwi/`.

On the physical board (ESP32-C3), with [arduino-cli](https://arduino.github.io/arduino-cli/):

```bash
cp firmware/coldtrack/secrets.example.h firmware/coldtrack/secrets.h   # edit; never commit
arduino-cli core install esp32:esp32 \
  --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli lib install "DHT sensor library" "Adafruit Unified Sensor"
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/coldtrack
arduino-cli upload  --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc -p COM5 firmware/coldtrack
```

On the physical board with a DHT11, uncomment `#define DHT_TYPE DHT11` in `secrets.h`. The OLED
screen and ThingSpeak MQTT are optional and require the U8g2 and PubSubClient libraries. Wi-Fi, sensor
ID and sensor key are written over the USB cable from the dashboard (Sensors, Connect sensor by cable).
Full step-by-step guide: [`docs/implantacao.md`](docs/implantacao.md).

### API

```bash
cd cloud/function
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp local.settings.example.json local.settings.json   # fill in with a development database
func start                                           # http://localhost:7071/api
```

Requires Python 3.11 and Azure Functions Core Tools v4. More details in
[`cloud/function/README.md`](cloud/function/README.md).

### Tests and lint

```bash
cd cloud/function
python -m unittest -v
pip install ruff==0.17.4 && ruff check .
```

GitHub Actions (`testes.yml`) runs the lint, the API tests and compiles the firmware for both
sensor variants (DHT22 for the simulation and DHT11 for the board) on every push and pull request.

### Climate analysis

See [`analise/README.md`](analise/README.md).

## Deployment

- **API**: the `publicar-api.yml` workflow runs the tests and publishes to the Function App on every
  push to the `main` branch that changes `cloud/function/`. Azure login uses OIDC, accepted only
  for `main` and for `everson` (a fallback that no longer triggers deployment). Manual deployment:
  `bash cloud/function/publicar.sh`.
- **Dashboard**: published by the [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi) repository,
  also on every push to `main`.
- **Infrastructure**: `infra/main.bicep` documents the environment; do not apply it without `what-if`
  (see [`infra/README.md`](infra/README.md)).

Workflow: branch off `main`, pull request to `main` with green tests.
The `everson` branch stays as a deployment fallback and must not be deleted. Protecting `main`
(required pull request and tests) needs a repository administrator; the command is in
[`CONTRIBUTING.md`](CONTRIBUTING.md), along with the commit convention.

## Security

- Wi-Fi credentials and the sensor key are not in the code. Each sensor has its own key,
  generated in the dashboard; the database stores only the hash.
- Passwords use scrypt with a per-user salt; JWT tokens last 8 hours and are revoked on logout
  (`POST /sair`) or password change. From the 5th wrong password the account enters an increasing
  wait (1 to 15 min), and each IP has an attempt limit.
- Each company sees only its own data; access is checked by the API on every call.
- Controls, fixes from the review and known limitations: [`docs/seguranca.md`](docs/seguranca.md).

## Status

- [x] Architecture definition
- [x] ESP32-C3 simulation on Wokwi
- [x] Temperature and humidity reading
- [x] LED alert system
- [x] JSON upload over HTTPS to Azure
- [x] Offline storage of readings and resend
- [x] Web dashboard published on Azure
- [x] Login with roles (logistics operator, manager and driver linked to a vehicle)
- [x] Climate analysis of the route (INMET) and preliminary thermal risk model
- [x] Sensor temperature forecast 10 min ahead (`GET /api/predict/sensor`), compared with persistence; with the current data it does not beat it yet
- [x] Automated tests and firmware build on GitHub Actions
- [x] Multiple companies with separated data, company registration and per-sensor key
- [x] Range per cargo profile (mango, grape) sent to the sensor
- [x] Password change, login lockout and QR label per vehicle
- [x] Heat forecast along the route (Open-Meteo + INMET history) on the dashboard
- [x] Site chat with an Azure OpenAI language model, answering from the project documentation
- [x] Dashboard assistant (Azure OpenAI), with the data of the logged-in user's company
- [x] Push alerts on the phone (Web Push) when a sensor gets worse
- [x] Device heartbeat when the sensor fails (`POST /api/heartbeat`)
- [x] Company deletion by the manager (`DELETE /api/empresa`)
- [x] Logical database backup with restore tested in CI
- [ ] Physical assembly
- [ ] Recycled enclosure
- [ ] Field tests
- [ ] Technical report

## Documentation

| document | contents |
|---|---|
| [`docs/como-funciona.md`](docs/como-funciona.md) | single study guide: how each layer works, from firmware to AI, with answers for the panel's question bank |
| [`docs/funcionalidades.md`](docs/funcionalidades.md) | feature mapping: everything the platform does, by layer |
| [`docs/apresentacao.md`](docs/apresentacao.md) | project presentation as slides, with the demonstration script ([.pptx version](docs/apresentacao.pptx)) |
| [`docs/stack-tecnica.md`](docs/stack-tecnica.md) | architecture, components, data model, deployment |
| [API Swagger](https://func-coldtrack-7319.azurewebsites.net/api/docs) | interactive route documentation (OpenAPI 3.0, `cloud/function/openapi.json`) |
| [`docs/api.md`](docs/api.md) | text reference of the API routes, with the rules in detail |
| [`docs/seguranca.md`](docs/seguranca.md) | security controls and known limitations |
| [`docs/ux/`](docs/ux/) | preliminary user research: [secondary research](docs/ux/pesquisa-secundaria.md), [simulated interviews](docs/ux/entrevistas-simuladas.md) and [persona, journey and value proposition](docs/ux/persona-jornada-proposta.md); script in [`docs/pesquisa-usuarios.md`](docs/pesquisa-usuarios.md) |
| [`docs/lgpd.md`](docs/lgpd.md) | inventory of personal data, retention and data subject rights (LGPD) |
| [`docs/politica-de-privacidade.md`](docs/politica-de-privacidade.md) | privacy policy, data subject rights and how to request deletion |
| [`docs/slides/previa-tecnica.pdf`](docs/slides/previa-tecnica.pdf) | technical preview slides (English pitch and presentation blocks) |
| [`docs/pitch-en.md`](docs/pitch-en.md) | two-minute pitch script in English |
| [`docs/model-card.md`](docs/model-card.md) | model card of the thermal risk model and of the sensor forecast model (English) |
| [`docs/implantacao.md`](docs/implantacao.md) | step-by-step guide to put a carrier into operation |
| [`docs/memorial-descritivo.md`](docs/memorial-descritivo.md) | design report of the prototype |
| [`cloud/function/README.md`](cloud/function/README.md) | API: run, test and publish |
| [`infra/README.md`](infra/README.md) | Azure resources, estimated monthly cost and OIDC deployment |
| [`analise/README.md`](analise/README.md) | climate analysis of the route |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | branches, commits and checks |
| [Dashboard documentation](https://github.com/mbalbuquerque/Front-End-pi#readme) | README, architecture, user guide and test report of the front end |

## Team

Faculdade Senac PE, Integrative Project, 4th term (2026.2).
Advisor: Arnot Caiado.

- Enzo Antônio
- Everson
- Emmanuel Luís
- Gabriel Eduardo
- José Allamberg
- Marcelo Barbosa
