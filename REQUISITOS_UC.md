# Matriz de requisitos das UCs (5º período)

Situação em 16/11/2026, para a prévia técnica do PI. Cada linha traz o requisito, onde ele está
implementado e a evidência observável. Status: **Atendido** (há evidência), **Parcial** (existe,
mas falta parte da exigência) ou **Pendente** (sem evidência). Exigência sem evidência é tratada
como pendente e entra no `PLANO_ACAO.md`.

Os dois repositórios do projeto:
back-end/firmware/infra (`projeto-integrador-4-periodo`) e painel web (`Front-End-pi`).

## IoT

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| IOT-01 | Dispositivo com ≥ 2 sensores | `firmware/coldtrack/coldtrack.ino` | Um sensor DHT11/DHT22 (temperatura e umidade) | Parcial |
| IOT-02 | Esquema elétrico | `firmware/wokwi/diagram.json` | Simulação no Wokwi | Atendido |
| IOT-03 | Intervalo de leitura justificado e leitura inválida tratada | `coldtrack.ino` (`INTERVALO_ENVIO`, `lerSensor`) | Leitura a cada 20 s; leitor com checagem de checksum e duas tentativas | Atendido |
| IOT-04 | Canal ThingSpeak recebendo dados reais, intervalo ≥ 15 s | `coldtrack.ino` (MQTT) | Canal 3515173 | Atendido |
| IOT-05 | Envio à API em nuvem | `POST /api/telemetria` | Leituras gravadas no Cosmos DB | Atendido |
| IOT-06 | Base com ≥ 48 h de coleta e estatística descritiva | — | Sem evidência na base de sensor | Pendente |

## Cloud Computing

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| CLD-01 | API publicada em HTTPS, configuração por variáveis de ambiente | `cloud/function`, `infra/main.bicep` | Function App com `httpsOnly`; `local.settings.example.json` | Atendido |
| CLD-02 | Segredos fora do código | `secrets.example.h`, app settings | `secrets.h` fora do Git | Atendido |
| CLD-03 | Dockerfile | `infra/Dockerfile` | Imagem oficial de Azure Functions; build executado no CI a cada push | Atendido |
| CLD-04 | Deploy automático pelo CI | `.github/workflows/publicar-api.yml` | Login OIDC, publica a branch `everson` | Atendido |
| CLD-06 | Logs centralizados | `infra/main.bicep` | Application Insights ligado a um workspace do Log Analytics, retenção de 90 dias | Atendido |
| CLD-07 | Contêiner com reinício automático e verificação de saúde | `infra/docker-compose.yml` | `restart: unless-stopped` e healthcheck em `/api/health`; ainda não testado na máquina da equipe | Parcial |
| CLD-08 | `.env.example` na raiz | `.env.example` | Nomes das variáveis, sem valores reais | Atendido |
| CLD-05 | Rota de saúde | `GET /api/health` | 200 com o banco no ar, 503 sem; testes automatizados | Atendido |

## Segurança de Sistemas de Informação

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| SEG-01 | Autenticação JWT | `cloud/function/seguranca.py` | Token HS256, sessão revogável | Atendido |
| SEG-02 | 401, 403 e 400 corretos | `function_app.py`, `test_acesso.py`, `test_seguranca.py` | Testes automatizados | Atendido |
| SEG-03 | Usuário só acessa dados da própria empresa | filtro por `empresaId` em toda consulta | Item de outra empresa responde 404 | Atendido |
| SEG-04 | Modelo de ameaças (STRIDE) do fluxo principal | `docs/stride.md` | Tabela por categoria, com controle e risco residual | Atendido |
| SEG-05 | Limite de requisições | `limites.py` | Login, chat e assistente | Parcial |
| SEG-06 | LGPD | `docs/lgpd.md` | Inventário de dados, retenção e direitos do titular; faltam política de privacidade e exclusão da empresa | Parcial |
| SEG-07 | Dependências verificadas e varredura ZAP | `.github/workflows/seguranca.yml` | pip-audit e ZAP baseline com relatório como artefato; resultado a registrar depois da primeira execução | Parcial |

## Qualidade de Software

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| QS-01 | Testes automatizados das rotas principais no CI | `.github/workflows/testes.yml` | Lint, testes e cobertura a cada push e PR | Atendido |
| QS-02 | Cobertura | `pytest --cov-fail-under=98` | Exigência do CI no back-end | Atendido |
| QS-03 | Plano de testes | `docs/qa/`, `docs/relatorio-de-testes.md` (front) | Métricas e relatório; falta um plano formal | Parcial |
| QS-04 | Registro de defeitos com severidade e ambiente | `.github/ISSUE_TEMPLATE/bug.yml`, etiquetas `sev:*` e `amb:*` | Template nos dois repositórios | Atendido |

## Inteligência Artificial

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| IA-01 | Problema de IA definido que apoia uma decisão | `analise/` | Risco térmico por mês e hora na rota Petrolina–Suape (dados do INMET, 2019–2025); apoia o horário de saída. Ainda não usa as leituras do sensor | Parcial |
| IA-02 | Baseline calculado | `analise/relatorio.md` | Modelo ingênuo (média geral), Brier 0,202 | Atendido |
| IA-03 | Divisão temporal e métrica melhor que o baseline | `analise/explorar.py` | Treino 2019–2022, teste 2023–2025; Brier 0,091 (55% menos erro) | Atendido |
| IA-04 | Model card | `docs/model-card.md` | Uso, dados, métricas e limitações | Atendido |
| IA-05 | `/predict` e resultado no painel | — | Não existe | Pendente |

## UE Mobile

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| MOB-01 | App autenticando e listando leituras reais | `Front-End-pi` (PWA: `manifest.json`, `sw.js`) | PWA com login, consumindo a API publicada | Atendido |
| MOB-02 | Protótipo navegável | PWA em produção | O PWA funcional serve como protótipo navegável; não há arquivo no Figma (entendimento da equipe) | Atendido |

## Comportamento do Consumidor

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| CC-01 | Persona, jornada e proposta de valor com pesquisa | `docs/pesquisa-usuarios.md` | Roteiro e formulário prontos; respostas ainda não coletadas | Pendente |

## Tech English

| ID | Requisito | Onde está | Evidência | Status |
|---|---|---|---|---|
| ENG-01 | README em inglês | `Readme_English` (raiz de cada repositório) | Arquivo adicionado na `main`; README principal aponta para ele | Atendido |
| ENG-02 | Documentação da API em inglês | `cloud/function/openapi.json` | Resumo em inglês no início da documentação; as descrições de cada rota seguem em português | Parcial |
| ENG-03 | Pitch de 2 min em inglês | `docs/pitch-en.md` | Roteiro e esqueleto de 6 slides | Parcial |
| ENG-04 | Model card em inglês | `docs/model-card.md` | Escrito em inglês | Atendido |
