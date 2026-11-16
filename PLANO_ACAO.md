# Plano de ação

Criado em 16/11/2026, a partir da matriz `REQUISITOS_UC.md` e do `RESILIENCIA.md`. Prazo do
documento: 22/11, 23h59. Será revisado depois da devolutiva escrita (até 18/11). Responsável
em branco = ainda não definido pela equipe.

| Lacuna | UC / critério | Ação concreta | Responsável | Prazo | Evidência de conclusão |
|---|---|---|---|---|---|
| Tag `v0.9-previa` não criada | Entrega | Mergear o PR da matriz, criar a tag nos dois repositórios e enviar o link | | 16/11 | Tags no GitHub (#29) |
| F1 e F3 sem execução registrada | IoT / Resiliência | Rodar os dois testes na placa e anotar tempos | | 23/11 | Tabela preenchida em `RESILIENCIA.md` (#34) |
| Sem número de sequência | IoT / R3 | Incluir sequência no payload e no contrato da API | | 25/11 | Teste automático de lacuna na sequência (#35) |
| Sem watchdog | IoT / R4 | Ativar watchdog de tarefa e testar reinício | | 25/11 | F2 aprovado (#35) |
| Sem `/health`, heartbeat e status online/offline | IoT, Cloud / R6, R7 | Rota `/api/health`, heartbeat do sensor e status no painel | | 27/11 | Rota no OpenAPI; painel com "sem dados desde HH:MM" (#36, Front #13) |
| Sem backup do banco | Cloud / R8 | Configurar backup do Cosmos DB e testar restauração | | 27/11 | Procedimento documentado (#36) |
| Dockerfile ainda não validado no CI | Cloud | Dockerfile em `infra/` e build no CI | | 16/11 | CI verde (#31) |
| Sem compose, logs centralizados e custo mensal | Cloud (final) | Compose com API e emulador; registrar logs e custo | | 28/11 | `docker-compose.yml`; estimativa em `infra/README.md` (#31) |
| Sem ZAP, dependências e LGPD | Segurança | Varredura ZAP; verificação de dependências; seção de LGPD (STRIDE já em `docs/stride.md`) | | 25/11 | Relatório ZAP (#32) |
| Sem modelo de IA sobre o sensor | IA | Definir problema, baseline, modelo, `/predict` e model card | | 28/11 | Notebook e métrica contra o baseline (#37) |
| Sem pesquisa com usuários | Consumidor | ≥ 5 entrevistas ou ≥ 20 respostas; persona e jornada | | 25/11 | Registro da pesquisa (#38) |
| Sem alertas push e estado offline no app | UE Mobile (final) | Push por limiar e faixa "sem conexão" no PWA | | 28/11 | Demonstração no celular (Front #13) |
| Sem teste de usabilidade | UE Mobile / Consumidor (final) | Teste com 5 usuários e SUS | | 28/11 | Relatório SUS ≥ 68 (#38) |
| OpenAPI, README e slides em inglês | Tech English | OpenAPI em inglês, README `.md`, slides e vídeo (roteiro em `docs/pitch-en.md`) | | 25/11 | Itens publicados (#33) |
| Base de ≥ 48 h e segundo sensor | IoT / Dados | Exportar coleta, estatística descritiva, campo de origem; confirmar sensores | | 25/11 | CSV e relatório (#39) |
| Cobertura do painel e PRs revisados | Qualidade (final) | Cobertura do painel no CI; revisão de PRs por outro membro | | 28/11 | CI com mínimo; PRs com aprovação (Front #12) |
| Deploy ainda parte da `everson` | Cloud / Qualidade | Publicar a partir da `main` e proteger a branch | | 28/11 | Workflow na `main` (#40) |
