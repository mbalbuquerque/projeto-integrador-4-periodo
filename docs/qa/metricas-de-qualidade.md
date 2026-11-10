# Dados da coleta: métricas de qualidade do ColdTrack

Coleta feita em 10/11/2026. Período analisado: de 16/09/2026 (primeiro commit) a 10/11/2026.
Repositórios: `mbalbuquerque/projeto-integrador-4-periodo` (back) e `mbalbuquerque/Front-End-pi` (front), branch main.
O back já inclui o PR #20 (testes da QA).

## Tamanho (cloc, linhas não vazias e sem comentário, só arquivos versionados)

Ficaram fora da contagem:
- `*.json`, incluindo o `openapi.json` gerado e o `base_chat.json`
- lockfiles, `*.yml`, `*.toml`, `*.md`, `*.txt`, `*.bicep`, `*.sh`
- `azure_ca.h` (certificado) e `secrets.example.h`
- arquivos de configuração do Vite, ESLint e Playwright

Código de produção:

| Módulo | LOC |
|---|---|
| API `cloud/function/*.py` (7 arquivos) | 1.472 |
| Scripts da API | 268 |
| Análise `analise/*.py` | 262 |
| Firmware `coldtrack.ino` | 1.053 |
| Firmware `payload_core.h` | 58 |
| Painel JSX (`src`) | 4.641 |
| Painel JS (`src`, sem testes) | 1.450 |
| Painel `public/sw.js` | 49 |
| Painel CSS (`src/styles`) | 3.575 |
| Painel `index.html` | 20 |
| **Total de produção** | **12.848 = 12,848 KLOC** |

Código de teste, contado à parte, soma 6.225 linhas:
- back: 2.398
- front: 3.827

## 1. Densidade de defeitos

Critério: defeito é um commit `fix:` que corrige algo já entregue.
- Foram 20 commits `fix` no total, 10 em cada repositório.
- Dois deles corrigem o mesmo defeito: o RSSI inválido, consertado uma vez na API e outra no firmware. Por isso são 19 defeitos.
- Resultado: 19 ÷ 12,848 = **1,48 defeito/KLOC**. Por repositório: back 9 ÷ 3,113 = 2,89 e front 10 ÷ 9,735 = 1,03.

A severidade foi classificada pela equipe durante a coleta:

| Commit | Defeito | Severidade |
|---|---|---|
| 0f4dd7f + 883c744 | RSSI impossível gravado como número; passou a ser enviado como `null` | Média |
| 881f79e | Login respondia mais rápido para e-mail inexistente, o que permitia descobrir e-mails cadastrados | Alta (segurança) |
| 3ac31f8 | Firmware não lia a faixa quando havia espaço depois dos dois-pontos | Alta |
| 4d8d73a | Chat devolvia fontes numa recusa sem contexto | Baixa |
| 9f19cdf | Assistente não lia número com vírgula decimal | Baixa |
| d7e043e | Login sem espera crescente e sem limite por IP | Alta (segurança) |
| e9277cf | Sessão não era derrubada no servidor; redefinição de senha frágil | Alta (segurança) |
| e356105 | Dados da empresa entravam no prompt da IA sem marcação de não confiáveis; links não eram filtrados | Média |
| 6b9c811 | E-mails completos apareciam nos logs da API | Média |
| b2366d0 | Card de status desalinhado em tela larga | Baixa |
| 9ca4202 | Script de publicação quebrava no Windows | Média |
| e9edc31 | Sensor sem leituras aparecia como erro de conexão | Média |
| 4df247f | Faltava o espaço entre o ícone e a marca no login | Baixa |
| cbc9033 | Botão "Sensores" do chat não achava a resposta | Baixa |
| 5e91187 | Rotas limpas do site publicado não respondiam 200 | Média |
| e079fa1 | Erro de concordância no aviso de relatório | Baixa |
| c6276cd | Textos do FAQ desatualizados | Baixa |
| 4d51edd | Fluxo de dados mostrava ThingSpeak no lugar da API | Baixa |
| c608999 | Monitoramento usava o canal antigo do ThingSpeak | Média |

Total por severidade: 4 alta, 7 média, 8 baixa.

Limitações:
- Não existe issue de bug no período, então um defeito corrigido sem commit `fix` não entra na contagem.
- O ambiente em que cada defeito foi encontrado não foi registrado.
- O produto ainda não tem cliente, então nenhum defeito chegou a produção com usuário real.

## 2. Cobertura de testes (cobertura de linhas)

| Módulo | Linhas cobertas / total | Linhas | Ramos | Ferramenta |
|---|---|---|---|---|
| API | 1.143 / 1.146 | 99,7% | 99,7% | pytest-cov, 230 testes |
| Análise | 109 / 207 | 52,7% | 40,9% | pytest-cov, 7 testes |
| Painel (`src`) | 1.556 / 8.045 | 19,3% | 88,2%* | Vitest com v8, 158 testes |
| Painel, só `src/lib` | 502 / 515 | 97,5% | 92,8% | idem |
| Firmware | não medido | | | 4 testes C++ (19 asserts) |
| **Total medido** | **2.808 / 9.398** | **29,9%** | | |

\* O valor de ramos do painel engana: os arquivos JSX sem teste quase não têm ramos contados.

Observações:
- As telas do painel são testadas por e2e com Playwright: 224 execuções simuladas e 57 testes contra o site em produção. A cobertura de linhas não mede esses testes.
- Os testes do firmware validam uma cópia das funções num header (`payload_core.h`) que o `coldtrack.ino` ainda não inclui.

## 3. Retrabalho e 4. Produtividade

Horas estimadas, não apontadas:
- Commits com menos de 2 h de intervalo entre si formam uma sessão.
- Cada sessão vale do primeiro ao último commit, mais 0,5 h.
- Somando os dois repositórios e juntando as sessões sobrepostas, dá **26,3 h**.
- Isso é um piso: estudo, reunião, montagem da placa e trabalho sem commit ficam de fora.
- Os 14 commits da QA têm o mesmo horário e por isso contam só 0,5 h.

Retrabalho:
- Horas de retrabalho = fatia de commits `fix`: 20 de 181 commits únicos, ou 11,05%, que dá 2,9 h.
- Taxa: 2,9 ÷ 26,3 = **11,0%**.
- A reescrita do painel para React (PR #5) e a melhoria de segurança planejada não entram, porque são evolução e não correção.

Produtividade, abordagem A:
- Entrega concluída = PR mergeado na main com CI verde.
- Back: PRs #15 a #20, que são 6. Front: PRs #1, #2, #4, #5, #6, #7 e #8, que são 7. Total: 13.
- 13 ÷ 26,3 = **0,49 entrega/h**.
- Os PRs vão de +6 a +18.967 linhas.
- LOC/hora não foi usado, porque as horas não são medidas.

## Custo do retrabalho

2,9 h × R$ 40,00/h = **R$ 116,00**.

O custo-hora é simulado: um desenvolvedor júnior com encargos. Como as horas são piso, o custo também é. Com 11% de retrabalho, cada 100 h de equipe custam R$ 440,00 em correção.

## Comandos

- `npx cloc --vcs=git --by-file --csv .`
- `pytest --cov=. --cov-branch --cov-report=json`, rodado em `cloud/function`
- `pytest analise --cov=analise --cov-branch`
- `npx vitest run --coverage --coverage.include='src/**' --coverage.exclude='**/*.test.js'`, numa cópia temporária com `@vitest/coverage-v8@2.1.9`
- `git log --all --no-merges --numstat`
- `gh pr list --state merged`
