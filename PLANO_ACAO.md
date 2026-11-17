# Plano de ação

Criado em 16/11/2026, a partir da matriz `REQUISITOS_UC.md` e do `RESILIENCIA.md`. Prazo do
documento: 22/11, 23h59. Será revisado depois da devolutiva escrita (até 18/11). Responsável
em branco = ainda não definido pela equipe.

| Lacuna | UC / critério | Ação concreta | Responsável | Prazo | Evidência de conclusão |
|---|---|---|---|---|---|
| F3 sem execução registrada | IoT / Resiliência | F1 e F3 aprovados na placa física em 17/11 (tempos em `RESILIENCIA.md`); falta medir perda em 24 h e disponibilidade junto com a base de 48 h (#39) | | 23/11 | Tabela preenchida em `RESILIENCIA.md` (#34) |
| Watchdog validado só no simulador | IoT / R4 | Repetir F2 (queda de energia) e um travamento na placa física | | 25/11 | F2 aprovado (#35) |
| Modelo do sensor não supera o baseline | IA | `GET /api/predict/sensor` publicada com as leituras reais; MAE 0,342 °C contra 0,313 °C da persistência. Re-treinar depois da coleta de 48 h e mostrar a previsão no painel (Front-End-pi #60) | | 28/11 | Modelo com leituras do sensor (#37) |
| Pesquisa só secundária e simulada | Consumidor | Validar persona e jornada (`docs/ux/`) com ≥ 5 entrevistas ou ≥ 20 respostas reais | | 25/11 | Registro da pesquisa (#38) |
| Sem teste de usabilidade | UE Mobile / Consumidor (final) | Teste com 5 usuários e SUS | | 28/11 | Relatório SUS ≥ 68 (#38) |
| Vídeo em inglês | Tech English | OpenAPI, slides do pitch e `README.en.md` já em inglês; falta o vídeo de até 5 min (roteiro em `docs/pitch-en.md`) | | 25/11 | Itens publicados (#33) |
| Base de ≥ 48 h e segundo sensor | IoT / Dados | Base e estatística já em `analise/sensor/` (8,5 h reais); deixar a placa coletando ≥ 48 h seguidas e regerar; confirmar sensores | | 25/11 | CSV e relatório (#39) |
| Cobertura do painel e PRs revisados | Qualidade (final) | Cobertura do painel em 99,2% de linhas (mínimo de 98% no CI, medido em 17/11); falta revisão de PRs por outro membro | | 28/11 | CI com mínimo; PRs com aprovação (Front #12) |
| `main` sem proteção | Cloud / Qualidade | Exigir pull request e testes verdes na `main` dos dois repositórios (depende de um administrador; comando em `CONTRIBUTING.md`) | | 28/11 | Regra de proteção ativa |

## Concluídas desde 16/11

| Lacuna | Evidência |
|---|---|
| Sequência validada só no simulador (R3) | F1 na placa física em 17/11: `seq` 89 a 128 contínua e `lacunas: []` (`RESILIENCIA.md`) |
| Heartbeat do firmware (R7) | `POST /api/heartbeat` e envio pela placa com o sensor em falha (firmware 2026.11.17.2, #35); aviso no painel |
| Backup do banco sem restauração testada (R8) | Backup lógico com restauração testada no CI (`infra/backup/`, `backup-logico.yml`, #36); restauração de produção e do backup periódico seguem não testadas |
| Limites restantes | `POST /empresas` (5 por hora por IP) e `POST /senha` (espera do login) com testes de 429 |
| Sem alertas push | Web Push publicado na API (`/api/push/*`) e no painel (Front-End-pi #13) |
| Deploy ainda parte da `everson` | Os dois workflows publicam a cada push na `main` (#40); a `everson` fica como credencial de reserva |
