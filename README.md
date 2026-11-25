# ColdTrack Edge

Monitoramento da cadeia fria no transporte refrigerado de frutas (manga e uva do Vale do
São Francisco). Um nó sensor com ESP32-C3 mede temperatura e umidade dentro do baú,
classifica a leitura pela faixa da carga, sinaliza na placa e envia a telemetria para uma
API no Azure. Um painel web mostra as leituras, os alertas e os cadastros de cada empresa.

Projeto Integrador do 4º período, Faculdade Senac PE, 2026.2.

English version: [README.en.md](README.en.md).

O projeto tem dois repositórios:

| repositório | conteúdo |
|---|---|
| [projeto-integrador-4-periodo](https://github.com/mbalbuquerque/projeto-integrador-4-periodo) (este) | firmware do ESP32-C3, API (Azure Functions, Python), infraestrutura, análise climática e documentação |
| [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi) | painel web (React + Vite) publicado no Azure Storage |

Os dois são publicados pela branch `main` (ver [Publicação](#publicação)).

| | endereço |
|---|---|
| Painel publicado | <https://stcoldtrackweb7319.z15.web.core.windows.net> |
| API (documentação interativa, Swagger) | <https://func-coldtrack-7319.azurewebsites.net/api/docs> |
| API (base) | `https://func-coldtrack-7319.azurewebsites.net/api` |
| Simulação no Wokwi | <https://wokwi.com/projects/475352296477619201> |
| Canal no ThingSpeak (placa física via MQTT) | <https://thingspeak.mathworks.com/channels/3515173> |

## Arquitetura

```
 ESP32-C3 + DHT11/DHT22                          Azure (rg-coldtrack, Brazil South)
 +-----------------------+    HTTPS + JSON     +--------------------------------+
 | lê a cada ciclo       |  x-device-key       | Azure Function (Python 3.11)   |
 | classifica pela faixa | ------------------> | POST /api/telemetria           |
 | LEDs ou tela OLED     | <------------------ | valida, classifica, grava      |
 | fila em flash (sem    |  status + faixa     +---------------+----------------+
 | rede, reenvia depois) |                                     |
 +-----------+-----------+                                     v
             |                                 +--------------------------------+
             | MQTT/TLS (opcional)             | Cosmos DB for NoSQL            |
             v                                 | empresas, usuarios, veiculos,  |
       ThingSpeak                              | dispositivos, viagens, leituras|
                                               +---------------+----------------+
                                                               ^
 Navegador (painel)          token JWT                         |
 +-----------------------+   Authorization: Bearer   +---------+----------------+
 | site estático no      | ------------------------> | rotas do painel na mesma |
 | Azure Storage ($web)  |                           | Azure Function           |
 +-----------------------+                           +--------------------------+
```

O painel é uma aplicação React + Vite (repositório [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi)).
A API é a única fonte dos dados: o painel não lê o ThingSpeak, que aparece apenas na tela
Monitoramento (com login) e no envio MQTT opcional do firmware. Os perfis de carga
(manga, uva, demonstrativo) definem a faixa de temperatura de cada veículo; a API envia a
faixa ao sensor a cada leitura.

O chat do site (`POST /api/chat`) responde dúvidas sobre o projeto com um modelo de linguagem
do Azure OpenAI (`gpt-4.1-mini`), usando como contexto trechos desta documentação (busca por
embeddings); se a IA não responder, o site usa o FAQ. Dentro do painel, o assistente do painel (`POST /api/assistente`, com login) responde
sobre o uso das telas e sobre os dados da própria empresa (sensores, leituras, veículos e
viagens), sem executar ações.

Detalhes de cada camada: [`docs/stack-tecnica.md`](docs/stack-tecnica.md). Rotas da API: [Swagger](https://func-coldtrack-7319.azurewebsites.net/api/docs) (interativo,
spec em [`cloud/function/openapi.json`](cloud/function/openapi.json)) e [`docs/api.md`](docs/api.md) (texto). Recursos do Azure: [`infra/README.md`](infra/README.md).

### Bibliotecas e dependências do projeto

| Camada | Arquivo de referência | Bibliotecas e ferramentas |
|---|---|---|
| Backend (produção) | [`cloud/function/requirements.txt`](cloud/function/requirements.txt) | `azure-functions==1.26.0`, `azure-cosmos==4.17.1`, `PyJWT==2.15.1`, `openai==3.46.0`, `azure-identity==1.27.0`, `pywebpush==2.5.0`, `pyotp==2.9.0` |
| Backend (testes e qualidade) | [`cloud/function/requirements-dev.txt`](cloud/function/requirements-dev.txt) | `pytest==9.2.0`, `pytest-cov==7.1.0`, `coverage==7.16.2`, `hypothesis==6.168.5`, `time-machine==3.5.1`, `openapi-spec-validator==0.9.0` (e no CI: `ruff==0.17.4`, `bandit==1.9.4`, `pip-audit==2.7.3`) |
| Análise climática | [`analise/requirements.txt`](analise/requirements.txt) | `pandas>=2.0` (`2.3.3`), `matplotlib>=3.7` (`3.10.9`) |
| Firmware (ESP32-C3) | [`firmware/coldtrack/coldtrack.ino`](firmware/coldtrack/coldtrack.ino), [`firmware/wokwi/libraries.txt`](firmware/wokwi/libraries.txt) | `DHT sensor library`, `Adafruit Unified Sensor`, core ESP32 (`WiFi.h`, `WiFiClientSecure.h`, `HTTPClient.h`, `LittleFS.h`, `Preferences.h`, `esp_task_wdt.h`, `esp_sntp.h`, `driver/gpio.h`, `time.h`) e opcionais (`PubSubClient.h` para MQTT/ThingSpeak, `U8g2` para OLED) |
| Frontend (painel web) | [`Front-End-pi`](https://github.com/mbalbuquerque/Front-End-pi) | React 18 + Vite, PWA (`public/manifest.json`, `public/sw.js`) e Web Serial API do navegador |

### Arquitetura e estrutura de cada camada

1. **ESP32-C3 (Firmware IoT)** — *Arquitetura embarcada orientada a ciclo não bloqueante (`millis()`)*:
   - Opera em loop contínuo (`setup()` / `loop()`) com leitura periódica, validação *Fail-Fast*, fila *store-and-forward* em `LittleFS` (até 500 leituras sem rede) e configurações persistidas em `Preferences`.
   - A lógica pura de montagem de JSON e classificação de faixa fica isolada em [`firmware/coldtrack/payload_core.h`](firmware/coldtrack/payload_core.h), permitindo testes unitários em C++ (`firmware/tests/test_firmware.cpp`) fora da placa.
   - Exemplo: `coldtrack.ino` lê o DHT11/DHT22 e chama `montarPayloadCore(buf, sizeof(buf), deviceId, temp, umid, rssi, medidoEm)` para gerar o JSON enviado via `WiFiClientSecure` + `HTTPClient` para `POST /api/telemetria`.

```mermaid
flowchart LR
    S["Sensor DHT11/DHT22"] --> L["Loop millis() + Fail-Fast"]
    L --> P["payload_core.h (montarPayloadCore)"]
    P -->|Com rede| H["WiFiClientSecure + HTTPClient (HTTPS)"]
    P -->|Sem rede| F["LittleFS (fila store-and-forward)"]
    F -->|Rede volta| H
    L --> LED["LEDs / OLED"]
```

2. **Frontend (Painel Web)** — *Arquitetura SPA baseada em componentes (React 18 + Vite + PWA)*:
   - A interface no repositório [`Front-End-pi`](https://github.com/mbalbuquerque/Front-End-pi) é organizada em componentes e páginas React que consomem a API REST via `fetch` com `Authorization: Bearer <token JWT>`, além de contar com manifesto e service worker para PWA.
   - Exemplo: a tela de login autentica em `POST /api/login` (com suporte a 2FA TOTP via `pyotp` na API) e armazena o JWT para consultar leituras, alertas e cadastros, além de usar Web Serial para gravar Wi-Fi, ID e chave do sensor via USB.

```mermaid
flowchart LR
    U["Navegador / PWA"] --> R["Componentes React (Vite)"]
    R -->|"fetch + Bearer JWT"| API["API Azure Functions"]
    R -->|"Web Serial (USB)"| ESP["ESP32-C3 (Preferences)"]
```

3. **Banco de Dados (Azure Cosmos DB for NoSQL)** — *Arquitetura orientada a documentos JSON*:
   - Os dados são armazenados em *containers* JSON definidos em [`infra/main.bicep`](infra/main.bicep) e [`infra/ci/preparar_banco.py`](infra/ci/preparar_banco.py), com chave de partição `/id` (`empresas`, `usuarios`, `veiculos`, `dispositivos`, `viagens`, `limites`) e `/deviceId` (`leituras`).
   - Exemplo de documento em `leituras` (particionado por `deviceId`):
     ```json
     {"id": "uuid", "deviceId": "coldtrack-01", "empresaId": "emp-teste", "temperatura": 12.4, "umidade": 81.0, "status": "NORMAL", "medidoEm": 1790464605}
     ```

```mermaid
flowchart TD
    DB["Cosmos DB: coldtrack"] --> C1["empresas (/id)"]
    DB --> C2["usuarios (/id)"]
    DB --> C3["veiculos (/id)"]
    DB --> C4["dispositivos (/id)"]
    DB --> C5["viagens (/id)"]
    DB --> C6["limites (/id)"]
    DB --> C7["leituras (/deviceId)"]
```

4. **Backend (API em Python / Azure Functions)** — *Arquitetura Serverless orientada a rotas (HTTP Triggers) e módulos de domínio*:
   - [`cloud/function/function_app.py`](cloud/function/function_app.py) atua como camada de entrada e roteamento HTTP, delegando regras de negócio para módulos de domínio (`contrato.py`, `cadastros.py`, `seguranca.py`, `limites.py`, `predicao.py`, `previsao_sensor.py`) e serviços externos (`chat.py`, `assistente.py`, `push.py`), persistindo diretamente no Cosmos DB.
   - Exemplo: a rota `telemetria(req)` em `function_app.py` valida a chave `x-device-key` usando `seguranca.py`, aplica a faixa de carga e classifica a leitura via `contrato.py`, grava no container `leituras` e dispara notificação Web Push (`push.py`) se houver piora de faixa.

```mermaid
flowchart LR
    REQ["HTTP Request (HTTPS)"] --> FA["function_app.py (HTTP Triggers)"]
    FA --> SEC["seguranca.py (JWT / x-device-key)"]
    FA --> DOM["Dominio (contrato.py, cadastros.py, predicao.py)"]
    FA --> SRV["Servicos (chat.py, assistente.py, push.py)"]
    DOM --> COS["Cosmos DB"]
    SRV --> AOAI["Azure OpenAI / Web Push"]
```

## Principais funcionalidades

1. **Coleta de telemetria na borda (ESP32-C3)** — [`firmware/coldtrack/payload_core.h`](firmware/coldtrack/payload_core.h#L18-L27): monta o payload JSON na placa com temperatura, umidade, RSSI do Wi-Fi e timestamp NTP para envio HTTPS (ou gravação na fila offline em `LittleFS`).
   ```cpp
   inline void montarPayloadCore(char *destino, size_t tamanho, const char *deviceId,
                                 float temperatura, float umidade, long rssi, time_t medidoEm,
                                 uint32_t seq = 0, const char *origem = "placa",
                                 float temperaturaBruta = NAN, float umidadeBruta = NAN) {
       char rssiJson[16];
       if (rssi < 0) {
           snprintf(rssiJson, sizeof(rssiJson), "%ld", rssi);
       } else {
           snprintf(rssiJson, sizeof(rssiJson), "null");
       }
   ```

2. **Classificação de faixa da carga e idempotência** — [`cloud/function/contrato.py`](cloud/function/contrato.py#L293-L300): classifica cada leitura em `NORMAL`, `ATENCAO` ou `CRITICO` conforme o perfil da carga (`manga`, `uva`, `demonstrativo`) e gera ID determinístico (`id_leitura`) para evitar duplicidade em reenvios.
   ```python
   def classificar(temperatura, perfil=PERFIL_PADRAO):
       f = faixa(perfil)
       minimo = f["min"] if f["min"] is not None else float("-inf")
       if minimo <= temperatura <= f["max"]:
           return "NORMAL"
       if minimo - f["margem"] <= temperatura <= f["max"] + f["margem"]:
           return "ATENCAO"
       return "CRITICO"
   ```

3. **Autenticação JWT, hash de senha e 2FA** — [`cloud/function/seguranca.py`](cloud/function/seguranca.py#L55-L83): protege senhas com `scrypt` e sal aleatório, emite tokens JWT (`HS256`) com escopo de empresa/perfil e valida 2FA TOTP.
   ```python
   def gerar_hash(senha):
       sal = os.urandom(16)
       derivada = hashlib.scrypt(senha.encode(), salt=sal, n=N, r=R, p=P, dklen=32)
       return f"scrypt${N}${R}${P}${_b64(sal)}${_b64(derivada)}"
   ```

4. **Alertas Web Push na piora de faixa** — [`cloud/function/push.py`](cloud/function/push.py#L178-L183): detecta transição para faixa mais grave (`NORMAL` -> `ATENCAO` -> `CRITICO`) e envia notificação push para os dispositivos inscritos da empresa.
   ```python
   def piorou(anterior, atual):
       return GRAVIDADE.get(atual, 0) > GRAVIDADE.get(anterior or "NORMAL", 0)
   ```

5. **Previsão térmica do sensor (10 min à frente)** — [`cloud/function/previsao_sensor.py`](cloud/function/previsao_sensor.py#L97-L104): estima a temperatura futura a partir das leituras recentes e classifica o status previsto.
   ```python
   def estimar(modelo, atrib):
       variacao = sum(c * atrib[nome] for nome, c in zip(modelo["atributos"], modelo["coeficientes"]))
       return atrib["y0"] + variacao
   ```

6. **Chat e assistente com RAG (Azure OpenAI)** — [`cloud/function/chat.py`](cloud/function/chat.py#L225-L229): busca por similaridade de cosseno os trechos mais relevantes da documentação vetorizada (`base_chat.json`) para contextualizar as respostas da IA.
   ```python
   def mais_proximos(vetor, base, k=TOP_K, minimo=SIMILARIDADE_MIN):
       notas = [(cosseno(vetor, item["vetor"]), n) for n, item in enumerate(base)]
       notas = sorted((p for p in notas if p[0] >= minimo), key=lambda p: -p[0])
       return [base[n] for _, n in notas[:k]]
   ```

7. **Backup lógico do Cosmos DB** — [`infra/backup/exportar.py`](infra/backup/exportar.py#L26-L37): exporta todos os containers para arquivos JSONL com manifesto de contagem e metadados.
   ```python
   def exportar(banco, saida, excluir=()):
       os.makedirs(saida, exist_ok=True)
       manifesto = {"versao": bc.VERSAO, "banco": banco.id, "data": bc.agora(), "containers": {}}
       inicio = time.monotonic()
       for props in banco.list_containers():
           nome = props["id"]
           if nome in excluir:
               continue
           container = banco.get_container_client(nome)
           arquivo = f"{nome}.jsonl"
           total = bc.escrever_jsonl(os.path.join(saida, arquivo), container.read_all_items())
   ```

8. **Heartbeat da placa e detecção de falha do sensor** — [`cloud/function/contrato.py`](cloud/function/contrato.py#L148-L165): recebe sinal de vida do ESP32-C3 (`POST /api/heartbeat`) mesmo quando o DHT11/DHT22 falha, registrando motivo e versão do firmware.
   ```python
   def validar_heartbeat(dados):
       if not isinstance(dados, dict):
           return ["corpo deve ser um objeto JSON"]

       erros = []
       device = dados.get("deviceId")
       if not isinstance(device, str) or not DEVICE_ID.match(device):
           erros.append("deviceId: texto de 3 a 40 caracteres (letras, números, _ ou -)")
       if dados.get("motivo") not in MOTIVOS_HEARTBEAT:
           erros.append("motivo: use " + ", ".join(MOTIVOS_HEARTBEAT))
   ```

9. **Gestão multiempresa, veículos, dispositivos e viagens** — [`cloud/function/cadastros.py`](cloud/function/cadastros.py#L192-L208): valida cadastros com isolamento por `empresaId` e perfis (`gestor`, `operador`, `motorista`).
   ```python
   def validar_viagem(dados):
       if not isinstance(dados, dict):
           return ["corpo deve ser um objeto JSON"], None
       erros = []
       veiculo = _texto(dados, "veiculo", 20, erros)
       origem = _texto(dados, "origem", 80, erros)
       destino = _texto(dados, "destino", 80, erros)
       carga = _texto(dados, "carga", 120, erros)
       inicio = _data(dados, "inicio", erros)
       fim = _data(dados, "fim", erros, obrigatorio=False)
       if inicio and fim and fim <= inicio:
           erros.append("fim: deve ser depois do início")
   ```

10. **Rate limiting compartilhado com plano B em memória** — [`cloud/function/limites.py`](cloud/function/limites.py#L65-L80): limita tentativas de login, chat e assistente por IP/empresa usando o container `limites` no Cosmos DB, com fallback local em `JanelaEmMemoria`.
    ```python
    class JanelaEmMemoria:
        def contar(self, doc_id, fim, somar, agora):
            with self._trava:
                if len(self._contas) > 5000:
                    for chave in [c for c, (_, f) in self._contas.items() if f <= agora]:
                        del self._contas[chave]
                n, _ = self._contas.get(doc_id, (0, fim))
                n += somar
                self._contas[doc_id] = (n, fim)
                return n
    ```

11. **Predição de risco térmico na rota (histórico INMET)** — [`cloud/function/predicao.py`](cloud/function/predicao.py#L53-L67): calcula probabilidade e nível de risco térmico por mês e hora da viagem, comparando com a baseline histórica.
    ```python
    def prever(modelo, mes, hora):
        prob = modelo["probabilidade"][mes - 1][hora]
        baseline = modelo["baseline"]
        return {
            "mes": mes,
            "hora": hora,
            "limiarC": modelo["limiarC"],
            "probabilidade": prob,
            "nivel": nivel(prob, modelo["niveis"]),
        }
    ```

12. **Restauração de backup lógico com trava anti-produção** — [`infra/backup/restaurar.py`](infra/backup/restaurar.py#L31-L44): restaura containers a partir dos JSONL exportados e do `manifesto.json`, bloqueando qualquer tentativa de gravação em endpoint de produção (`recusar_producao=True`).
    ```python
    def restaurar(cliente, pasta, nome_banco=None):
        with open(os.path.join(pasta, "manifesto.json"), encoding="utf-8") as f:
            manifesto = json.load(f)
        banco = cliente.create_database_if_not_exists(nome_banco or manifesto["banco"])
        resultado = {}
        for nome, meta in manifesto["containers"].items():
            container = banco.create_container_if_not_exists(
                nome, partition_key=PartitionKey(path=meta["chaveParticao"]),
                default_ttl=meta.get("ttl"))
            for doc in bc.ler_jsonl(os.path.join(pasta, meta["arquivo"])):
                container.upsert_item(doc)
            resultado[nome] = (meta["contagem"], contar(container))
        return resultado
    ```

## Estrutura do repositório

```
.
├── firmware/
│   ├── coldtrack/           firmware do ESP32-C3 (Arduino)
│   │   ├── coldtrack.ino
│   │   ├── azure_ca.h       certificado raiz usado no HTTPS
│   │   └── secrets.example.h  modelo do secrets.h (o real não vai para o Git)
│   └── wokwi/               circuito da simulação (diagram.json, libraries.txt)
├── cloud/function/          API (Azure Function em Python)
│   ├── function_app.py      rotas
│   ├── contrato.py          contrato da telemetria, perfis de carga e classificação
│   ├── seguranca.py         senha, token, espera do login, chave de sensor
│   ├── limites.py           limites de uso compartilhados (container limites)
│   ├── cadastros.py         validação dos cadastros
│   ├── chat.py              chat do site (Azure OpenAI + busca na base_chat.json)
│   ├── assistente.py        assistente do painel (dados da empresa + base do chat)
│   ├── base_chat.json       trechos da documentação com embeddings, usados pelo chat
│   ├── test_*.py            testes (unittest)
│   ├── pacote.txt           arquivos publicados no Azure
│   ├── publicar.sh          publicação manual
│   └── scripts/             scripts de suporte (criar usuário, migração)
├── infra/                   main.bicep do ambiente atual e notas de infraestrutura
├── analise/                 análise climática da rota (dados do INMET)
├── docs/                    documentação técnica, API, segurança, implantação, memorial descritivo
├── .gitleaks.toml           regras e allowlist de varredura de segredos (Gitleaks)
└── .github/workflows/       pipelines de CI/CD, testes, segurança, backup e publicação da API
```

### Estrutura exigida na entrega

As pastas não foram renomeadas para os nomes da entrega porque o caminho faz parte da
publicação (workflows, `pacote.txt`, links da documentação e do Wokwi). Correspondência:

| pasta exigida | onde está | conteúdo |
|---|---|---|
| `/firmware` | [`firmware/`](firmware/) | firmware do ESP32-C3, testes do firmware e circuito do Wokwi |
| `/backend` | [`cloud/function/`](cloud/function/) | API em Azure Functions (Python), testes e publicação |
| `/database` | [`docs/banco/`](docs/banco/) (diagrama ER, partições, índices, integridade, criação e dados de exemplo), [`infra/main.bicep`](infra/main.bicep) (Cosmos DB), [`infra/ci/preparar_banco.py`](infra/ci/preparar_banco.py), [`infra/ci/dados_exemplo.py`](infra/ci/dados_exemplo.py), [`infra/backup/`](infra/backup/), [`cloud/function/scripts/`](cloud/function/scripts/) | modelo de dados (Cosmos DB NoSQL), definição do banco e dos containers, carga de dados de exemplo sintéticos, backup lógico e restauração, migração |
| `/frontend` | repositório [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi) | painel web (React + Vite) |
| `/mobile` | repositório [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi) | o mesmo painel como PWA instalável no celular (`public/manifest.json`, `public/sw.js`); não há app nativo |
| `/ia` | [`analise/`](analise/), [`cloud/function/chat.py`](cloud/function/chat.py), [`cloud/function/assistente.py`](cloud/function/assistente.py) | análise climática da rota (dados do INMET) e chat/assistente com Azure OpenAI |
| `/infra` | [`infra/`](infra/), [`.github/workflows/`](.github/workflows/) | Bicep, Dockerfile, compose, backup e workflows de teste e publicação |
| `/docs` | [`docs/`](docs/) | documentação técnica, API, segurança, implantação |

## Usuário de teste

Não há conta pronta em produção (senha compartilhada no repositório seria um segredo exposto).
Para entrar no sistema:

- **Produção:** abra o [painel](https://stcoldtrackweb7319.z15.web.core.windows.net), use *Cadastrar empresa* e crie o gestor com um e-mail e uma senha de sua escolha. O gestor cria depois os operadores e motoristas em *Configurações*. A empresa e os dados criados podem ser excluídos pelo próprio gestor (*Configurações > Excluir empresa*).
- **Local ou CI (emulador do Cosmos):** `python infra/ci/preparar_banco.py` cria o gestor `gestor.teste@exemplo.com`, senha `SenhaDeTeste-123`. Ela é fictícia e só vale no emulador. `python infra/ci/dados_exemplo.py` acrescenta um sensor, um veículo, uma viagem e 12 leituras sintéticas (veja [`docs/banco/`](docs/banco/)).

## Como rodar

### Firmware

Na simulação, abrir o projeto no Wokwi (link acima). Para montar um projeto novo no Wokwi,
copiar `firmware/coldtrack/coldtrack.ino` (como `sketch.ino`), `azure_ca.h`, um `secrets.h`
feito a partir do `secrets.example.h` e os arquivos de `firmware/wokwi/`.

Na placa física (ESP32-C3), com o [arduino-cli](https://arduino.github.io/arduino-cli/):

```bash
cp firmware/coldtrack/secrets.example.h firmware/coldtrack/secrets.h   # editar; nunca commitar
arduino-cli core install esp32:esp32 \
  --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli lib install "DHT sensor library" "Adafruit Unified Sensor"
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/coldtrack
arduino-cli upload  --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc -p COM5 firmware/coldtrack
```

Na placa física com DHT11, descomentar `#define DHT_TYPE DHT11` no `secrets.h`. Tela OLED e
MQTT do ThingSpeak são opcionais e pedem as bibliotecas U8g2 e PubSubClient. Wi-Fi, ID e chave
do sensor são gravados pelo cabo USB a partir do painel (Sensores, Conectar sensor pelo cabo).
Passo a passo completo: [`docs/implantacao.md`](docs/implantacao.md).

### API

```bash
cd cloud/function
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp local.settings.example.json local.settings.json   # preencher com um banco de desenvolvimento
func start                                           # http://localhost:7071/api
```

Requer Python 3.11 e Azure Functions Core Tools v4. Mais detalhes em
[`cloud/function/README.md`](cloud/function/README.md).

### Docker e Docker Compose

Para buildar apenas a imagem da API (a partir da raiz do repositório, usando [`infra/Dockerfile`](infra/Dockerfile)):

```bash
docker build -f infra/Dockerfile -t coldtrack-api:1.0.0 cloud/function
```

Para subir a API junto com o emulador do Cosmos DB via [`infra/docker-compose.yml`](infra/docker-compose.yml):

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d --build
python infra/ci/preparar_banco.py
curl -s http://localhost:7071/api/health
```

### Testes e lint

```bash
cd cloud/function
python -m unittest -v
pip install ruff==0.17.4 && ruff check .
```

O GitHub Actions (`testes.yml`) roda o lint, os testes da API e compila o firmware nas duas
variantes de sensor (DHT22 da simulação e DHT11 da placa) a cada push e pull request.

### Análise climática

Ver [`analise/README.md`](analise/README.md).

## Publicação

- **API**: o workflow `publicar-api.yml` roda os testes e publica na Function App a cada push
  na branch `main` que altere `cloud/function/`. O login no Azure é por OIDC, aceito só para a
  `main` e para a `everson` (reserva, que não dispara mais a publicação). Publicação manual:
  `bash cloud/function/publicar.sh`.
- **Painel**: publicado pelo repositório [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi),
  também a cada push na `main`.
- **Infraestrutura**: `infra/main.bicep` documenta o ambiente; não aplicar sem `what-if`
  (ver [`infra/README.md`](infra/README.md)).

Fluxo de trabalho: branch a partir da `main`, pull request para a `main` com os testes verdes.
A `everson` fica como reserva da publicação e não deve ser apagada. A `main` está protegida
desde 23/11/2026 (regra de repositório: pull request e testes obrigatórios, sem force push); a
convenção de commits está em [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Nuvem

Resumo da infraestrutura em nuvem do ColdTrack: o que está publicado, como chega lá e quanto
custa. Os detalhes de cada recurso ficam em [`infra/README.md`](infra/README.md).

### 1. Sistema publicado

| | URL |
|---|---|
| Painel (site estático, HTTPS) | <https://stcoldtrackweb7319.z15.web.core.windows.net> |
| API (HTTPS) | <https://func-coldtrack-7319.azurewebsites.net/api> |
| Documentação da API (Swagger) | <https://func-coldtrack-7319.azurewebsites.net/api/docs> |
| Verificação de saúde | <https://func-coldtrack-7319.azurewebsites.net/api/health> |

As duas URLs só aceitam HTTPS: `httpsOnly` está ligado na Function App, e o site estático
fica no endpoint HTTPS do Azure Storage.

### 2. Provedor, serviços e modelo de serviço

Provedor: **Microsoft Azure**, assinatura *Azure for Students*, grupo de recursos
`rg-coldtrack`, região Brazil South.

| componente | serviço | modelo | por que este modelo |
|---|---|---|---|
| Frontend (painel React + PWA) | Azure Storage, site estático (`$web`) | PaaS | o painel é só HTML, CSS e JS compilados; servir arquivos não precisa de servidor próprio, e o Storage entrega HTTPS e escala sem configuração |
| Backend (API Python 3.11) | Azure Functions, plano Flex Consumption | PaaS (serverless) | a API é feita de rotas curtas chamadas pelos sensores a cada 20 s; o plano cobra por execução, cabe na franquia gratuita e escala sozinho. Nenhuma máquina virtual para atualizar |
| Banco de dados | Azure Cosmos DB for NoSQL (free tier) | PaaS | banco gerenciado: o Azure cuida de disco, réplica, atualização e backup; documentos JSON combinam com a telemetria do sensor; o free tier dá 1000 RU/s e 25 GB sem custo |
| Armazenamento de objetos | Azure Storage (Blob), conta `stcoldtrack7319` | PaaS | guarda o pacote publicado da função. O sistema não recebe arquivos de usuários, então não há outro bucket |
| IA do chat e do assistente | Azure OpenAI (`gpt-4.1-mini`, `text-embedding-3-small`) | PaaS | modelo hospedado e cobrado por token; a API entra com identidade gerenciada, sem chave |
| Logs e métricas | Application Insights + Log Analytics | SaaS | ferramenta pronta de observabilidade; a equipe só consulta, não opera nada |
| Identidade | Microsoft Entra ID | SaaS | login do GitHub Actions por OIDC e identidade gerenciada da Function |
| Código e CI/CD | GitHub + GitHub Actions | SaaS | repositório e execução do pipeline, fora do Azure |
| Sensor | ESP32-C3 + DHT (borda, IoT) | fora da nuvem | fica no baú do caminhão e fala com a API por HTTPS |

Não há IaaS: nenhum componente roda em máquina virtual gerenciada pela equipe. A escolha foi
deliberada. Com uma equipe de estudantes e sem plantão, cada servidor próprio seria mais um
sistema operacional para atualizar e proteger.

**Modelo de implantação: nuvem pública.** Todos os recursos ficam em um único provedor
público (Azure), em uma região. Não há data center próprio para justificar nuvem privada ou
híbrida, e um segundo provedor (multicloud) dobraria o trabalho de operação sem ganho para o
volume do piloto. A região Brazil South deixa os dados no Brasil (LGPD) e perto dos
caminhões, o que reduz a latência dos sensores.

### 3. Diagrama da arquitetura na nuvem

![Arquitetura na nuvem](docs/arquitetura-nuvem.png)

- O navegador baixa o painel do Storage e chama a API com o token JWT do login.
- O sensor envia cada leitura para a API com a chave própria dele (`x-device-key`).
- A API lê e grava no Cosmos DB, chama o Azure OpenAI com a identidade gerenciada e manda
  logs e métricas para o Application Insights.
- O GitHub Actions entra no Azure por OIDC (sem senha guardada) e publica a API e o painel.

### 4. Pipeline (GitHub Actions)

| workflow | quando roda | o que faz |
|---|---|---|
| [`testes.yml`](.github/workflows/testes.yml) | todo push e todo pull request, em qualquer branch | instala as dependências, roda o lint (ruff) e os testes da API com cobertura, os testes da análise climática, os testes unitários do firmware, compila o firmware para o ESP32-C3 e constrói a imagem Docker da API |
| [`publicar-api.yml`](.github/workflows/publicar-api.yml) | push na `main` que altere `cloud/function/` (ou manual) | roda os testes de novo, empacota, entra no Azure por OIDC, publica na Function App e confere `/api/health` |
| [`seguranca.yml`](.github/workflows/seguranca.yml) | toda segunda-feira, quando as dependências da API mudam, ou manual | procura vulnerabilidades conhecidas nas dependências (pip-audit) e roda o ZAP baseline na documentação da API |
| [`backup-logico.yml`](.github/workflows/backup-logico.yml) | pull request ou push que mexa em `infra/backup/` | exporta e restaura o banco no emulador do Cosmos para provar o backup lógico |
| [`compose-zap.yml`](.github/workflows/compose-zap.yml) | pull request que mexa na API ou na infraestrutura | sobe API + emulador com Docker Compose, testa o reinício do contêiner e roda o ZAP |
| [`ci-cd.yml`](.github/workflows/ci-cd.yml) | push/PR em `dev`, `homologacao` e `main` (ou manual) | pipeline unificado em 7 etapas com versões fixas (sem `:latest`): 1. Segurança e CVE (Gitleaks com [`.gitleaks.toml`](.gitleaks.toml), `pip-audit`, `bandit` e checagem de tags fixas); 2. Build e checagem (`ruff`, `compileall`, `docker compose config`, JSONs); 3. QA e testes (API com cobertura >= 98%, análise climática, backup lógico e firmware C++); 4. Segurança Docker (Buildx + Trivy `CRITICAL`); 5. Smoke test Docker (Compose + emulador Cosmos + `/api/health` e `/api/docs`); 6. Docker Compose build (`--no-cache`); 7. Deploy automático via OIDC (`homologacao` e `main`) com healthcheck e resumo |
| [`backup-mensal.yml`](.github/workflows/backup-mensal.yml) | último dia do mês às 03h00 BRT (`0 6 28-31 * *`) ou manual | exporta o backup lógico mensal do Cosmos DB via `infra/backup/exportar.py` (chave somente leitura), compacta em `.tar.gz`, valida integridade (`gzip -t`, `sha256sum`) e guarda como artefato por 30 dias |
| [`publicar-site.yml`](https://github.com/mbalbuquerque/Front-End-pi/blob/main/.github/workflows/publicar-site.yml) (repositório do painel) | push na `main` do painel | roda lint, testes e build do React e envia o resultado para o `$web` do Storage |

Execuções: aba **Actions** de cada repositório
([API](https://github.com/mbalbuquerque/projeto-integrador-4-periodo/actions),
[painel](https://github.com/mbalbuquerque/Front-End-pi/actions)).

> **Secrets e variáveis adicionais do pipeline (`ci-cd.yml` e `backup-mensal.yml`)**: além das credenciais OIDC do Azure (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`), o backup mensal utiliza `COSMOS_ENDPOINT` e `COSMOS_READONLY_KEY` (e `vars.COSMOS_DATABASE`, padrão `coldtrack`). Opcionalmente, `NOTIFY_WEBHOOK_URL` envia o resumo do pipeline/backup por webhook, e `vars.HOMOLOG_*` / `vars.PROD_*` permitem customizar resource group, Function App e URL de healthcheck por ambiente.

O deploy é **automático a partir da `main`**. A credencial federada do Entra ID só aceita o
token emitido para a `main` (e para a `everson`, reserva que não dispara publicação), então
um push em outra branch não consegue publicar. Mudanças entram por pull request, com os
testes rodando antes do merge.

### 5. Como refazer o deploy do zero

Em uma assinatura nova (detalhes e comandos em [`infra/README.md`](infra/README.md)):

1. `az group create -n rg-coldtrack -l brazilsouth` e um workspace do Log Analytics.
2. `az deployment group what-if` e depois `az deployment group create -g rg-coldtrack
   -f infra/main.bicep -p jwtSecret=<segredo> logAnalyticsWorkspaceId=<id do workspace>`: cria as
   contas de Storage, a Function App, o Cosmos DB com os containers, o Application Insights e o
   Azure OpenAI com as app settings.
3. Ligar o site estático na conta do painel (`az storage blob service-properties update
   --static-website --index-document index.html`) e atribuir à identidade da Function o papel
   *Cognitive Services OpenAI User* (comandos no `infra/README.md`).
4. Registrar o aplicativo `coldtrack-github-deploy` no Entra ID com papel *Contributor* só no grupo,
   criar a credencial federada da branch `main` e cadastrar `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` e
   `AZURE_SUBSCRIPTION_ID` nos secrets dos dois repositórios.
5. Rodar `publicar-api.yml` e `publicar-site.yml` pelo botão *Run workflow* (ou fazer push na `main`).
6. Conferir `GET /api/health` (`"banco": "ok"`) e fazer um login no painel.

### 6. Variáveis de ambiente

Os nomes estão em [`.env.example`](.env.example) (API) e no `.env.example` do painel, sem valor
real. Em produção, os valores ficam nas *app settings* da Function App e nos secrets do GitHub
Actions; nunca no código.

| variável | onde | para que |
|---|---|---|
| `COSMOS_CONNECTION`, `COSMOS_DATABASE`, `COSMOS_CONTAINER` | API | acesso ao banco |
| `JWT_SECRET` | API | assinatura dos tokens do painel |
| `AOAI_ENDPOINT`, `AOAI_DEPLOY_CHAT`, `AOAI_DEPLOY_EMBED`, `AOAI_API_VERSION` | API | chat e assistente |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | API | envio de logs e métricas |
| `AzureWebJobsStorage`, `DEPLOYMENT_STORAGE_CONNECTION_STRING` | API | runtime do Functions |
| `VITE_API_URL` | painel | endereço da API |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | secrets do GitHub | qual identidade o OIDC usa (não são senhas) |

**Desenvolvimento e produção** usam os mesmos nomes com valores diferentes:

| | desenvolvimento | produção |
|---|---|---|
| API | `.env` copiado do `.env.example` (Docker Compose com o emulador do Cosmos) ou `local.settings.json` (`func start`) | app settings da Function App |
| Banco | emulador do Cosmos DB, chave pública do emulador | Cosmos DB `cosmos-coldtrack-7319` |
| Painel | `.env.local` com `VITE_API_URL=http://localhost:7071/api` | build com a URL publicada |
| CORS | API local | só a origem do painel publicado |

### 7. Logs e verificação de saúde

- **Verificação de saúde:** `GET /api/health` consulta o Cosmos DB e responde `200` com
  `{"status": "ok", "banco": "ok"}`, ou `503` com `"banco": "indisponivel"`. O
  `publicar-api.yml` confere essa rota depois de cada publicação, e o contêiner local tem
  `healthcheck` com a mesma rota.
- **Logs em produção:** portal do Azure, Function App `func-coldtrack-7319` > *Monitoramento* >
  *Logs* (Application Insights, retenção de 90 dias). Consulta útil, em KQL:

  ```kusto
  requests | where timestamp > ago(1h) | summarize count() by name, resultCode
  ```

  Pela linha de comando: `az webapp log tail -g rg-coldtrack -n func-coldtrack-7319`, ou
  *Live Metrics* no Application Insights para ver as chamadas em tempo real.

### 8. Custos

Estimativa mensal em USD, região Brazil South, montada na
[Calculadora de Preços do Azure](https://azure.microsoft.com/pt-br/pricing/calculator/). O uso
atual é o medido de 17/10 a 16/11/2026. Prints da calculadora e premissas em
[`docs/custos/`](docs/custos/).

| serviço | configuração | uso atual (US$/mês) | 10x usuários (US$/mês) |
|---|---|---|---|
| Azure Functions | Flex Consumption, 2048 MB; 3.040 execuções e 3.536 GB-s (atual), 30.390 e 35.350 GB-s (10x) | 0,00 | 0,00 |
| Azure Cosmos DB | NoSQL, 1000 RU/s provisionadas, free tier; 1 GB (atual), 10 GB (10x) | 0,00 | 0,00 |
| Storage | Blob, GPv2, LRS, Hot; 1 GB e 25 mil operações (atual), 10 GB e 253 mil (10x) | 0,06 | 0,62 |
| Azure Monitor (Log Analytics) | 0,07 GB/mês (atual), 0,7 GB/mês (10x), retenção de 90 dias | 0,03 | 0,28 |
| Azure OpenAI | GPT 4.1 mini, Global; 171 mil tokens de entrada e 2,5 mil de saída (atual), 10x isso | 0,07 | 0,72 |
| **Total mensal** | | **0,16** (R$ 0,87) | **1,62** (R$ 8,71) |

![Calculadora: uso atual](docs/custos/cenario-atual-resumo.png)

![Calculadora: 10x usuários](docs/custos/cenario-10x-resumo.png)

O custo é quase zero porque o uso cabe nas franquias gratuitas da Function (100 mil GB-s e
250 mil execuções por mês), no free tier do Cosmos (1000 RU/s e 25 GB) e nos 5 GB gratuitos
do Log Analytics (a calculadora não desconta essa franquia, por isso mostra alguns centavos no item). O único item cobrado desde já é o Azure OpenAI, por token. A estimativa de uma
operação real (10 caminhões ligados 24 h) fica em [`infra/README.md`](infra/README.md#uma-transportadora-com-10-caminhões).

### Escalabilidade

- **API:** o Flex Consumption escala **horizontalmente e de forma automática**: cada pico de
  chamadas abre novas instâncias, até 100 (`maximumInstanceCount` no `main.bicep`), e volta a zero
  quando não há uso. A escala **vertical** é escolher a memória da instância (hoje 2048 MB; o plano
  aceita 512, 2048 e 4096 MB).
- **Banco:** 1000 RU/s compartilhadas no banco. O uso medido é de menos de 1 RU/s, e 10 caminhões
  enviando a cada 20 s dariam cerca de 6 RU/s. Acima disso a vazão sobe no portal (manual) ou com
  *autoscale*. As leituras são particionadas por `deviceId`, o que espalha a carga quando o número
  de sensores cresce.
- **Painel:** arquivos estáticos no Storage, sem servidor; o próprio Azure escala a entrega.
- **Limites atuais:** a cota do Azure OpenAI (20 mil tokens por minuto por modelo) e os tetos de
  uso da API (10 perguntas por minuto por IP no chat, 300 por dia por empresa no assistente);
  passar das 1000 RU/s sai do free tier e passa a ser cobrado; a primeira chamada depois de um
  período parado tem *cold start*, porque não há instância sempre pronta.

### Acesso e menor privilégio

- O GitHub Actions entra por OIDC com papel *Contributor* **só no grupo** `rg-coldtrack`, e só
  para a branch `main`. Não há senha do Azure guardada no GitHub.
- A Function usa identidade gerenciada com o papel *Cognitive Services OpenAI User* (chama os
  modelos, não altera o recurso); a chave de API do Azure OpenAI está desligada.
- Cada sensor tem chave própria, e o banco guarda só o hash dela. Usuários do painel têm perfis
  (gestor, operador, motorista), e cada empresa só enxerga os próprios dados.
- O CORS da API aceita só a origem do painel publicado.
- O workflow de testes roda com `contents: read`; só o de publicação pede `id-token: write`.

### Backups

- **Periódico (gerenciado):** o Cosmos DB faz cópia a cada 4 h, guarda 8 h e replica o
  armazenamento do backup em outra região (Geo). A restauração é por chamado ao suporte.
- **Lógico (testado):** `infra/backup/exportar.py` exporta cada container para JSONL e
  `infra/backup/restaurar.py` restaura em outro banco; o workflow `backup-logico.yml` prova os dois
  no emulador. Detalhes, RPO e RTO em [`infra/README.md`](infra/README.md#backup-e-restauração-r8).

## Segurança

- Credenciais de Wi-Fi e a chave do sensor não ficam no código. Cada sensor tem chave própria,
  gerada no painel; o banco guarda só o hash.
- Senhas com scrypt e sal por usuário; tokens JWT de 8 horas, derrubados ao sair
  (`POST /sair`) ou trocar a senha. A partir da 5ª senha errada a conta entra em espera
  crescente (1 a 15 min), e cada IP tem limite de tentativas.
- Cada empresa só enxerga os próprios dados; o acesso é conferido pela API em toda chamada.
- Controles, correções da revisão e limitações conhecidas: [`docs/seguranca.md`](docs/seguranca.md).

## Status

- [x] Definição da arquitetura
- [x] Simulação ESP32-C3 no Wokwi
- [x] Leitura de temperatura e umidade
- [x] Sistema de alerta com LEDs
- [x] Envio em JSON via HTTPS para o Azure
- [x] Armazenamento das leituras sem conexão e reenvio
- [x] Dashboard web publicado no Azure
- [x] Login com perfis (operador logístico, gestor e motorista vinculado a um veículo)
- [x] Análise climática da rota (INMET) e modelo preliminar de risco térmico
- [x] Previsão da temperatura do sensor 10 min à frente (`GET /api/predict/sensor`), comparada com a persistência; com os dados atuais ainda não a supera
- [x] Testes automáticos e compilação do firmware no GitHub Actions
- [x] Várias empresas com dados separados, cadastro de empresa e chave por sensor
- [x] Faixa por perfil de carga (manga, uva) enviada ao sensor
- [x] Troca de senha, bloqueio de login e etiqueta QR por veículo
- [x] Previsão de calor na rota (Open-Meteo + histórico INMET) no dashboard
- [x] Chat do site com modelo de linguagem do Azure OpenAI, respondendo pela documentação do projeto
- [x] Assistente do painel (Azure OpenAI), com os dados da empresa de quem está logado
- [x] Alertas push no celular (Web Push) quando um sensor piora de faixa
- [x] Heartbeat da placa com o sensor em falha (`POST /api/heartbeat`)
- [x] Exclusão da empresa pelo gestor (`DELETE /api/empresa`)
- [x] Backup lógico do banco com restauração testada no CI
- [ ] Montagem física
- [ ] Gabinete reciclado
- [ ] Testes de campo
- [ ] Relatório técnico

## Documentação

| documento | conteúdo |
|---|---|
| [`docs/como-funciona.md`](docs/como-funciona.md) | guia único de estudo: como cada camada funciona, do firmware à IA, com respostas para o banco de perguntas da banca |
| [`docs/funcionalidades.md`](docs/funcionalidades.md) | mapeamento de funcionalidades: tudo o que a plataforma faz, por camada |
| [`docs/apresentacao.md`](docs/apresentacao.md) | apresentação do projeto em slides, com roteiro da demonstração ([versão .pptx](docs/apresentacao.pptx)) |
| [`docs/stack-tecnica.md`](docs/stack-tecnica.md) | arquitetura, componentes, modelo de dados, publicação |
| [Swagger da API](https://func-coldtrack-7319.azurewebsites.net/api/docs) | documentação interativa das rotas (OpenAPI 3.0, `cloud/function/openapi.json`) |
| [`docs/api.md`](docs/api.md) | referência das rotas da API em texto, com as regras em detalhe |
| [`docs/seguranca.md`](docs/seguranca.md) | controles de segurança e limitações conhecidas |
| [`docs/ux/`](docs/ux/) | pesquisa de usuários preliminar: [pesquisa secundária](docs/ux/pesquisa-secundaria.md), [entrevistas simuladas](docs/ux/entrevistas-simuladas.md) e [persona, jornada e proposta de valor](docs/ux/persona-jornada-proposta.md); coleta real: [roteiro](docs/ux/roteiro-pesquisa-real.md) e [registro das respostas](docs/ux/respostas-pesquisa-real.md) (vazio); rodada simulada: [respostas, síntese e SUS simulados](docs/ux/respostas-pesquisa-simulada.md); roteiro em [`docs/pesquisa-usuarios.md`](docs/pesquisa-usuarios.md) |
| [`docs/lgpd.md`](docs/lgpd.md) | inventário dos dados pessoais, retenção e direitos do titular |
| [`docs/politica-de-privacidade.md`](docs/politica-de-privacidade.md) | política de privacidade, direitos do titular e como pedir a exclusão |
| [`docs/slides/previa-tecnica.pdf`](docs/slides/previa-tecnica.pdf) | slides da prévia técnica (pitch em inglês e blocos da apresentação) |
| [`docs/implantacao.md`](docs/implantacao.md) | passo a passo para pôr uma transportadora em operação |
| [`docs/memorial-descritivo.md`](docs/memorial-descritivo.md) | memorial descritivo do protótipo |
| [`cloud/function/README.md`](cloud/function/README.md) | API: rodar, testar e publicar |
| [`infra/README.md`](infra/README.md) | recursos do Azure, custo mensal estimado e publicação por OIDC |
| [`analise/README.md`](analise/README.md) | análise climática da rota |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | branches, commits e verificações |
| [Documentação do painel](https://github.com/mbalbuquerque/Front-End-pi#readme) | README, arquitetura, guia de uso e relatório de testes do front |

## Equipe

Faculdade Senac PE, Projeto Integrador, 4º período (2026.2).
Professor orientador: Arnot Caiado.

- Enzo Antônio
- Everson
- Emmanuel Luís
- Gabriel Eduardo
- José Allamberg
- Marcelo Barbosa
