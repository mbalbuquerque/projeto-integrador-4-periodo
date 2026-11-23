# Matriz de requisitos das UCs (5º período)

Situação em 23/11/2026 (criada para a prévia técnica do PI e revisada depois dela). Cada linha traz o requisito, onde ele está
implementado e a evidência observável. Status: **Atendido** (há evidência), **Parcial** (existe,
mas falta parte da exigência) ou **Pendente** (sem evidência). Exigência sem evidência é tratada
como pendente e entra no `PLANO_ACAO.md`.

Os dois repositórios do projeto:
back-end/firmware/infra (`projeto-integrador-4-periodo`) e painel web (`Front-End-pi`).

## IoT

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| IOT-01 | Dispositivo com ≥ 2 sensores | `firmware/coldtrack/coldtrack.ino` | Um sensor DHT11/DHT22 (temperatura e umidade) mais o RSSI do Wi-Fi. O professor liberou o uso de um único sensor para a equipe (decisão de 23/11, issue #127 encerrada) | Atendido |
| IOT-02 | Esquema elétrico | `firmware/wokwi/diagram.json` | Simulação no Wokwi | Atendido |
| IOT-03 | Intervalo de leitura justificado e leitura inválida tratada | `coldtrack.ino` (`INTERVALO_ENVIO`, `lerSensor`) | Leitura a cada 20 s; leitor com checagem de checksum e duas tentativas | Atendido |
| IOT-04 | Canal ThingSpeak recebendo dados reais, intervalo ≥ 15 s | `coldtrack.ino` (MQTT) | Canal 3515173 | Atendido |
| IOT-05 | Envio à API em nuvem | `POST /api/telemetria` | Leituras gravadas no Cosmos DB | Atendido |
| IOT-06 | Base com ≥ 48 h de coleta e estatística descritiva | `analise/sensor/` (CSV do canal 3515173 com campo `origem`, `relatorio.md`; `relatorio_cosmos.md` com a coleta gravada no Cosmos) | Soma de 69,0 h cobertas no ThingSpeak (12.730 leituras) e 73,4 h de período no Cosmos (11.710 leituras, 17/11 a 20/11), com estatística descritiva, faltantes e inválidos medidos. Não há trecho contínuo de 48 h (o maior tem 10,3 h); a meta foi lida como 48 h de coleta somadas. Confirmar essa leitura com o professor | Atendido (soma de horas) |

## Cloud Computing

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| CLD-01 | API publicada em HTTPS, configuração por variáveis de ambiente | `cloud/function`, `infra/main.bicep` | Function App com `httpsOnly`; `local.settings.example.json` | Atendido |
| CLD-02 | Segredos fora do código | `secrets.example.h`, app settings | `secrets.h` fora do Git | Atendido |
| CLD-03 | Dockerfile | `infra/Dockerfile` | Imagem oficial de Azure Functions; build executado no CI a cada push | Atendido |
| CLD-04 | Deploy automático pelo CI | `.github/workflows/publicar-api.yml` (back), `publicar-site.yml` (front) | Login OIDC; publica a cada merge na `main` | Atendido |
| CLD-06 | Logs centralizados | `infra/main.bicep` | Application Insights ligado a um workspace do Log Analytics, retenção de 90 dias | Atendido |
| CLD-07 | Contêiner com reinício automático e verificação de saúde | `infra/docker-compose.yml`, `.github/workflows/compose-zap.yml` | Compose com a API e o emulador do Cosmos sobe no CI; healthcheck `healthy`; queda do processo volta a responder em 4,4 s (medido no CI, detalhes em `infra/README.md`) | Atendido |
| CLD-08 | `.env.example` na raiz | `.env.example` | Nomes das variáveis, sem valores reais | Atendido |
| CLD-05 | Rota de saúde | `GET /api/health` | 200 com o banco no ar, 503 sem; testes automatizados | Atendido |

## Segurança de Sistemas de Informação

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| SEG-01 | Autenticação JWT | `cloud/function/seguranca.py` | Token HS256, sessão revogável | Atendido |
| SEG-02 | 401, 403 e 400 corretos | `function_app.py`, `test_acesso.py`, `test_seguranca.py` | Testes automatizados | Atendido |
| SEG-03 | Usuário só acessa dados da própria empresa | filtro por `empresaId` em toda consulta | Item de outra empresa responde 404 | Atendido |
| SEG-04 | Modelo de ameaças (STRIDE) do fluxo principal | `docs/stride.md` | Tabela por categoria, com controle e risco residual | Atendido |
| SEG-05 | Limite de requisições | `limites.py`, `docs/seguranca.md` | Login, cadastro de empresa (`POST /empresas`, por IP), troca de senha (`POST /senha`, na espera do login), exclusão de empresa, chat, assistente, motorista, heartbeat e previsão do sensor; tabela rota × limite documentada; respostas 429 cobertas por testes automatizados | Atendido |
| SEG-06 | LGPD | `docs/lgpd.md`, `docs/politica-de-privacidade.md` | Inventário, retenção, direitos do titular e política de privacidade; exclusão da empresa pelo gestor (`DELETE /api/empresa` e seção "Excluir empresa" em Configurações, com o nome da empresa e a senha atual); exportação dos dados ainda manual | Atendido |
| SEG-07 | Dependências verificadas e varredura ZAP | `.github/workflows/seguranca.yml`, `docs/relatorio-seguranca.md` | pip-audit e npm audit sem achados; ZAP baseline com 0 alertas altos e 12 avisos triados | Atendido |

## Qualidade de Software

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| QS-01 | Testes automatizados das rotas principais no CI | `.github/workflows/testes.yml` | Lint, testes e cobertura a cada push e PR | Atendido |
| QS-02 | Cobertura | `pytest --cov-fail-under=98` (back), limites no `vite.config.js` (painel) | Exigência do CI: 98% no back-end (medido 99,8% em 17/11) e 98% de linhas no painel (medido 99,2%) | Atendido |
| QS-03 | Plano de testes | `docs/qa/plano-de-testes.md` | Plano formal com níveis, critérios, casos F1–F6, casos de segurança, rastreabilidade e ISO/IEC 25010 | Atendido |
| QS-04 | Registro de defeitos com severidade e ambiente | `.github/ISSUE_TEMPLATE/bug.yml`, etiquetas `sev:*` e `amb:*` | Template nos dois repositórios | Atendido |

## Inteligência Artificial

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| IA-01 | Problema de IA definido que apoia uma decisão | `analise/` | Risco térmico por mês e hora na rota Petrolina–Suape (dados do INMET, 2019–2025); apoia o horário de saída. Com as leituras reais do sensor (canal 3515173) há a previsão da temperatura 10 min à frente (`GET /api/predict/sensor`), retreinada em 23/11 com a coleta de 17 a 20/11 (4.211 amostras, teste de 1.267), que ainda não supera o baseline de persistência (MAE 0,334 °C contra 0,319 °C; outras tentativas também não, ver `docs/model-card.md`); sem ganho, o modelo não é recomendado (#37) | Parcial |
| IA-02 | Baseline calculado | `analise/relatorio.md` | Modelo ingênuo (média geral), Brier 0,202 | Atendido |
| IA-03 | Divisão temporal e métrica melhor que o baseline | `analise/explorar.py` | Treino 2019–2022, teste 2023–2025; Brier 0,091 (55% menos erro) | Atendido |
| IA-04 | Model card | `docs/model-card.md` | Uso, dados, métricas e limitações | Atendido |
| IA-05 | `/predict` e resultado no painel | `cloud/function/predicao.py`, `GET /api/predict`; card "Risco térmico da saída" no painel | Rota autenticada com o modelo exportado (`modelo_risco.json`) e card no dashboard; `GET /api/predict/sensor` publicada, exibição no painel em andamento (Front-End-pi #60) | Atendido |

## UE Mobile

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| MOB-01 | App autenticando e listando leituras reais | `Front-End-pi` (PWA: `manifest.json`, `sw.js`) | PWA com login, consumindo a API publicada; tela do motorista (`/motorista`) e alertas push (Web Push) | Atendido |
| MOB-02 | Protótipo navegável | PWA em produção | O PWA funcional serve como protótipo navegável; não há arquivo no Figma (entendimento da equipe) | Atendido |

## Comportamento do Consumidor

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| CC-01 | Persona, jornada e proposta de valor com pesquisa | `docs/ux/` | Pesquisa secundária com 13 fontes públicas e 5 entrevistas simuladas, identificadas como simuladas; persona, jornada e proposta de valor derivadas. Questionário (`roteiro-pesquisa-real.md`) aplicado a 5 respondentes simulados, com tarefas e SUS simulados (média 73,5), em `respostas-pesquisa-simulada.md`, por decisão da equipe em 17/11 (#38). Não houve coleta com usuários reais; em 23/11 a equipe decidiu manter a pesquisa simulada e declarada como tal | Parcial |

## Tech English

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| ENG-01 | README em inglês | `README.en.md` (raiz de cada repositório) | Tradução do README, com link no início do README em português | Atendido |
| ENG-02 | Documentação da API em inglês | `cloud/function/openapi.json`, `/api/docs` | Resumo, títulos e descrições de todas as rotas em inglês; teste no CI (`test_openapi.py`) | Atendido |
| ENG-03 | Pitch de 2 min em inglês | `docs/pitch-en.md`, `docs/slides/previa-tecnica.pdf` | Roteiro e 6 slides em inglês (parte 1 dos slides da prévia) | Atendido |
| ENG-04 | Model card em inglês | `docs/model-card.md` | Escrito em inglês | Atendido |
