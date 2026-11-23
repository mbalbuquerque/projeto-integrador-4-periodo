# Relatório de qualidade por característica (ISO/IEC 25010:2023)

Situação em 23/11/2026. Complementa a seção 12 do [`plano-de-testes.md`](plano-de-testes.md): lá estão
os casos; aqui, o que cada característica tem de evidência medida e o que ainda falta. Os números
foram medidos nesta data, no repositório da API e no do painel (`Front-End-pi`).

## Números medidos

| Medida | Valor | Como foi obtido |
|---|---|---|
| Testes automatizados da API | 439 aprovados (93 subtestes) | `pytest --cov=. --cov-branch` em `cloud/function`, 23/11 |
| Cobertura da API (linhas e ramos) | 99,83%; o CI exige no mínimo 98% | mesma execução; `--cov-fail-under=98` em `testes.yml` |
| Cobertura do painel | piso no CI: 98% de linhas, instruções e funções, 94% de ramos; 99,2% de linhas medidos em 17/11 | `npm run test:cobertura`, limites em `vite.config.js` |
| Testes do painel | 65 arquivos de teste unitário e 29 especificações e2e (Playwright) | `src/**/*.test.*` e `coldtrack-qa/` |
| Lint | ruff (API) e ESLint com `--max-warnings 0` (painel): sem apontamento | `testes.yml` dos dois repositórios |
| Análise estática de segurança (bandit) | 0 alertas altos; 3 médios de baixa confiança (B608, consulta montada com campos fixos e parâmetros `@`) e 1 baixo (B105, URL de escopo do Azure OpenAI, não é senha) | `bandit -r cloud/function`, 23/11; o CI bloqueia severidade e confiança médias ou mais |
| Dependências | `pip-audit` sem achado; `npm audit` sem alerta alto, com 2 moderados em `react-router` | workflow `Segurança` |
| ZAP | 0 altos (baseline em produção e varredura ativa em contêiner de teste) | [`relatorio-seguranca.md`](../relatorio-seguranca.md) |
| Histórico do Git | nenhum segredo real nos dois repositórios (conferido em 23/11) | [`relatorio-seguranca.md`](../relatorio-seguranca.md) |
| Integração contínua | `Testes`, `Compose e ZAP` e `Publicar` verdes na `main` dos dois repositórios em 22/11 | Actions |

## Por característica

| Característica | Evidência | Lacuna | Situação |
|---|---|---|---|
| Adequação funcional | 439 testes de rota, de contrato, de propriedade e de regra de negócio; classificação térmica; e2e do painel contra a API simulada e relatório de e2e em produção ([`relatorio-e2e-producao.md`](relatorio-e2e-producao.md)); rastreio ponta a ponta feito na prévia | Sensor único (IOT-01); `/predict` do sensor ainda não supera o baseline | Parcial |
| Eficiência de desempenho | Intervalo de leitura de 20 s justificado; limites de requisição por rota; consultas parametrizadas e filtradas por empresa e por dispositivo | Sem medida de latência, vazão nem consumo; sem teste de carga | Parcial |
| Compatibilidade | E2E em Chromium (1280 px e 390 px); PWA; spec OpenAPI validada no CI (`test_openapi.py`); `GET /api/health` para monitoração | Outros navegadores e outros sensores não testados | Parcial |
| Interação (usabilidade) | E2E de fluxos e de responsividade; tela do motorista; etiquetas QR; estado "Sem dados desde HH:MM" | Pesquisa e SUS são simulados e declarados como tal; sem teste de usabilidade com usuários reais; sem auditoria de acessibilidade além de verificações pontuais | Parcial (declarado) |
| Confiabilidade | Fila em flash e reenvio; idempotência por `seq`; F1, F2 e F3 aprovados na placa física em 17/11 ([`RESILIENCIA.md`](../../RESILIENCIA.md)); contêiner com health check e reinício medido no CI (4,4 s); backup lógico com restauração testada no CI | F4 e F6 sem execução; perda em 24 h, disponibilidade e recuperação ainda sem medição consolidada; restauração do backup de produção não executada; watchdog só validado no simulador | Parcial |
| Segurança | JWT com sessão revogável; 401, 403, 400, 404 e 429 testados; isolamento por empresa; espera de login; STRIDE; ficha OWASP ([`owasp.md`](../owasp.md)); `pip-audit`, `npm audit`, ZAP e bandit; LGPD | 2FA (issue #113) e matriz completa de IDOR (issue #114) ainda não estão na `main`; sem teste de invasão; chave do sensor sem criptografia na flash | Parcial |
| Manutenibilidade | Lint em todo push; cobertura de 99,83% na API e de 99,2% no painel; documentação em `docs/`; PRs com CI obrigatório por convenção; modelo de commits e de issues; etiquetas de severidade | `main` ainda sem proteção de branch (exige um administrador do repositório); revisão de PR por outra pessoa não é obrigatória; sem teste do firmware ligado ao `.ino` além da compilação e dos testes unitários C++ | Parcial |
| Flexibilidade | Infraestrutura como código (Bicep); perfis de carga configuráveis (`GET /perfis`); empresa e veículo cadastráveis; Docker e compose | Implantação em outra assinatura não testada; outro microcontrolador não verificado | Parcial |
| Safety (segurança operacional) | Classificação normal, atenção e crítico e alerta de carga fora da faixa; leitura inválida nunca é gravada como válida (R5) e gera aviso; F3 aprovado na placa física | Alerta de ponta a ponta com carga real não verificado; sem análise de perigos formal | Parcial |

## Como reproduzir

```bash
# API
cd cloud/function
pip install -r requirements.txt -r requirements-dev.txt ruff==0.17.4 bandit
ruff check .
pytest --cov=. --cov-branch --cov-report=term-missing --cov-fail-under=98
bandit -q -r . -x ./test_*.py,./scripts --severity-level medium --confidence-level medium

# Painel (Node 20, a versão do CI)
npm ci && npm run lint && npm run test:cobertura && npm run build && npm run test:e2e
```

Observação: com Node 26 os testes que usam `localStorage` falham em máquina local; o CI roda em Node 20.

## Manutenção

Atualizar os números desta tabela quando uma das lacunas for fechada (F4, F6, perda em 24 h,
issues #113 e #114, proteção da `main`) e antes da tag `v1.0`, com a data da nova medição.
