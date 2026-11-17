# Plano de ação

Criado em 16/11/2026, a partir da matriz `REQUISITOS_UC.md` e do `RESILIENCIA.md`. Prazo do
documento: 22/11, 23h59. Será revisado depois da devolutiva escrita (até 18/11). Responsável
em branco = ainda não definido pela equipe.

| Lacuna | UC / critério | Ação concreta | Responsável | Prazo | Evidência de conclusão |
|---|---|---|---|---|---|
| F1 e F3 sem execução registrada | IoT / Resiliência | Rodar os dois testes na placa e anotar tempos | | 23/11 | Tabela preenchida em `RESILIENCIA.md` (#34) |
| Sequência validada só no simulador | IoT / R3 | Gravar o firmware com `seq` na placa (depois da API publicada) e repetir F1 conferindo `lacunas` vazio em `GET /leituras` | | 25/11 | F1 repetido; sequência sem lacunas no banco (#35) |
| Watchdog validado só no simulador | IoT / R4 | Repetir F2 (queda de energia) e um travamento na placa física | | 25/11 | F2 aprovado (#35) |
| Heartbeat do firmware | IoT, Cloud / R7 | Selo online/offline e último contato já na tela de sensores (Front #17); decidir se o firmware precisa de heartbeat próprio | | 27/11 | Tela de sensores com o selo (#36, Front #13) |
| Backup do banco sem restauração testada | Cloud / R8 | Testar e documentar a restauração do backup periódico do Cosmos DB | | 27/11 | Procedimento documentado (#36) |
| Backup e restauração | Cloud (final) | Compose já validado no CI (`compose-zap.yml`); falta restauração do Cosmos testada | | 28/11 | Procedimento documentado (#36) |
| Limites restantes | Segurança | ZAP ativo já no CI (0 altos); falta limite em `POST /empresas` e `POST /senha` | | 25/11 | Teste de limite no CI (#32) |
| Modelo de IA ainda não usa o sensor | IA | `/predict` e card no painel já publicados; treinar um modelo com as leituras do sensor quando houver base suficiente | | 28/11 | Modelo com leituras do sensor (#37) |
| Pesquisa só secundária e simulada | Consumidor | Validar persona e jornada (`docs/ux/`) com ≥ 5 entrevistas ou ≥ 20 respostas reais | | 25/11 | Registro da pesquisa (#38) |
| Sem alertas push | UE Mobile (final) | Faixa "sem conexão" no PWA já feita (Front #21); falta push por limiar | | 28/11 | Demonstração no celular (Front #13) |
| Sem teste de usabilidade | UE Mobile / Consumidor (final) | Teste com 5 usuários e SUS | | 28/11 | Relatório SUS ≥ 68 (#38) |
| README `.md` e vídeo em inglês | Tech English | OpenAPI e slides do pitch já em inglês (`docs/slides/`); falta README `.md` em inglês e vídeo de até 5 min (roteiro em `docs/pitch-en.md`) | | 25/11 | Itens publicados (#33) |
| Base de ≥ 48 h e segundo sensor | IoT / Dados | Base e estatística já em `analise/sensor/` (8,5 h reais); deixar a placa coletando ≥ 48 h seguidas e regerar; confirmar sensores | | 25/11 | CSV e relatório (#39) |
| Cobertura do painel e PRs revisados | Qualidade (final) | Cobertura do painel já em 81,7% de linhas com mínimo no CI; falta revisão de PRs por outro membro | | 28/11 | CI com mínimo; PRs com aprovação (Front #12) |
| Deploy ainda parte da `everson` | Cloud / Qualidade | Publicar a partir da `main` e proteger a branch | | 28/11 | Workflow na `main` (#40) |
