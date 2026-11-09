# ColdTrack Edge

Monitoramento da cadeia fria no transporte refrigerado de frutas (manga e uva do Vale do
São Francisco). Um nó sensor com ESP32-C3 mede temperatura e umidade dentro do baú,
classifica a leitura pela faixa da carga, sinaliza na placa e envia a telemetria para uma
API no Azure. Um painel web mostra as leituras, os alertas e os cadastros de cada empresa.

Projeto Integrador do 4º período, Faculdade Senac PE, 2026.2.

O projeto tem dois repositórios:

| repositório | conteúdo |
|---|---|
| [projeto-integrador-4-periodo](https://github.com/mbalbuquerque/projeto-integrador-4-periodo) (este) | firmware do ESP32-C3, API (Azure Functions, Python), infraestrutura, análise climática e documentação |
| [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi) | painel web (React + Vite) publicado no Azure Storage |

Os dois são publicados pela branch `everson` (ver [Publicação](#publicação)).

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
demonstrativa de Monitoramento e no envio MQTT opcional do firmware. Os perfis de carga
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
  na branch `everson` que altere `cloud/function/`. O login no Azure é por OIDC, aceito só para
  essa branch. Publicação manual: `bash cloud/function/publicar.sh`.
- **Painel**: publicado pelo repositório [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi),
  também a cada push na `everson`.
- **Infraestrutura**: `infra/main.bicep` documenta o ambiente; não aplicar sem `what-if`
  (ver [`infra/README.md`](infra/README.md)).

Fluxo de trabalho: commits na `everson`, pull request para a `main` quando a etapa fica pronta.
**A `everson` nunca deve ser apagada**, porque a publicação e o login por OIDC dependem dela.
Detalhes e convenção de commits em [`CONTRIBUTING.md`](CONTRIBUTING.md).

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
- [x] Login com perfis (operador logístico e gestor)
- [x] Análise climática da rota (INMET) e modelo preliminar de risco térmico
- [x] Testes automáticos e compilação do firmware no GitHub Actions
- [x] Várias empresas com dados separados, cadastro de empresa e chave por sensor
- [x] Faixa por perfil de carga (manga, uva) enviada ao sensor
- [x] Troca de senha, bloqueio de login e etiqueta QR por veículo
- [x] Previsão de calor na rota (Open-Meteo + histórico INMET) no dashboard
- [x] Chat do site com modelo de linguagem do Azure OpenAI, respondendo pela documentação do projeto
- [x] Assistente do painel (Azure OpenAI), com os dados da empresa de quem está logado
- [ ] Montagem física
- [ ] Gabinete reciclado
- [ ] Testes de campo
- [ ] Relatório técnico

## Documentação

| documento | conteúdo |
|---|---|
| [`docs/funcionalidades.md`](docs/funcionalidades.md) | mapeamento de funcionalidades: tudo o que a plataforma faz, por camada |
| [`docs/apresentacao.md`](docs/apresentacao.md) | apresentação do projeto em slides, com roteiro da demonstração ([versão .pptx](docs/apresentacao.pptx)) |
| [`docs/stack-tecnica.md`](docs/stack-tecnica.md) | arquitetura, componentes, modelo de dados, publicação |
| [Swagger da API](https://func-coldtrack-7319.azurewebsites.net/api/docs) | documentação interativa das rotas (OpenAPI 3.0, `cloud/function/openapi.json`) |
| [`docs/api.md`](docs/api.md) | referência das rotas da API em texto, com as regras em detalhe |
| [`docs/seguranca.md`](docs/seguranca.md) | controles de segurança e limitações conhecidas |
| [`docs/implantacao.md`](docs/implantacao.md) | passo a passo para pôr uma transportadora em operação |
| [`docs/memorial-descritivo.md`](docs/memorial-descritivo.md) | memorial descritivo do protótipo |
| [`cloud/function/README.md`](cloud/function/README.md) | API: rodar, testar e publicar |
| [`infra/README.md`](infra/README.md) | recursos do Azure e publicação por OIDC |
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
