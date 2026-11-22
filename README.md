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
└── .github/workflows/       testes (API e firmware) e publicação da API
```

### Estrutura exigida na entrega

As pastas não foram renomeadas para os nomes da entrega porque o caminho faz parte da
publicação (workflows, `pacote.txt`, links da documentação e do Wokwi). Correspondência:

| pasta exigida | onde está | conteúdo |
|---|---|---|
| `/firmware` | [`firmware/`](firmware/) | firmware do ESP32-C3, testes do firmware e circuito do Wokwi |
| `/backend` | [`cloud/function/`](cloud/function/) | API em Azure Functions (Python), testes e publicação |
| `/database` | [`infra/main.bicep`](infra/main.bicep) (Cosmos DB), [`infra/ci/preparar_banco.py`](infra/ci/preparar_banco.py), [`infra/backup/`](infra/backup/), [`cloud/function/scripts/`](cloud/function/scripts/) | definição do banco e dos containers, carga do ambiente de teste, backup lógico e restauração, migração |
| `/frontend` | repositório [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi) | painel web (React + Vite) |
| `/mobile` | repositório [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi) | o mesmo painel como PWA instalável no celular (`public/manifest.json`, `public/sw.js`); não há app nativo |
| `/ia` | [`analise/`](analise/), [`cloud/function/chat.py`](cloud/function/chat.py), [`cloud/function/assistente.py`](cloud/function/assistente.py) | análise climática da rota (dados do INMET) e chat/assistente com Azure OpenAI |
| `/infra` | [`infra/`](infra/), [`.github/workflows/`](.github/workflows/) | Bicep, Dockerfile, compose, backup e workflows de teste e publicação |
| `/docs` | [`docs/`](docs/) | documentação técnica, API, segurança, implantação |

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
A `everson` fica como reserva da publicação e não deve ser apagada. A proteção da `main` (pull
request e testes obrigatórios) depende de um administrador do repositório; o comando está em
[`CONTRIBUTING.md`](CONTRIBUTING.md), junto com a convenção de commits.

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
| [`publicar-site.yml`](https://github.com/mbalbuquerque/Front-End-pi/blob/main/.github/workflows/publicar-site.yml) (repositório do painel) | push na `main` do painel | roda lint, testes e build do React e envia o resultado para o `$web` do Storage |

Execuções: aba **Actions** de cada repositório
([API](https://github.com/mbalbuquerque/projeto-integrador-4-periodo/actions),
[painel](https://github.com/mbalbuquerque/Front-End-pi/actions)).

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
