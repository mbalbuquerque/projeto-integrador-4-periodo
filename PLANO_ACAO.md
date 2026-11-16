# Plano de ação

Criado em 16/11/2026, a partir da matriz `REQUISITOS_UC.md` e do `RESILIENCIA.md`. Prazo do
documento: 22/11, 23h59. Será revisado depois da devolutiva escrita (até 18/11). Responsável
em branco = ainda não definido pela equipe.

| Lacuna | UC / critério | Ação concreta | Responsável | Prazo | Evidência de conclusão |
|---|---|---|---|---|---|
| F1 e F3 sem execução registrada | IoT / Resiliência | Rodar os dois testes na placa e anotar tempos | | 23/11 | Tabela preenchida em `RESILIENCIA.md` (#34) |
| Sem número de sequência | IoT / R3 | Incluir sequência no payload e no contrato da API | | 25/11 | Teste automático de lacuna na sequência (#35) |
| Sem watchdog | IoT / R4 | Ativar watchdog de tarefa e testar reinício | | 25/11 | F2 aprovado (#35) |
| Heartbeat do firmware | IoT, Cloud / R7 | Selo online/offline e último contato já na tela de sensores (Front #17); decidir se o firmware precisa de heartbeat próprio | | 27/11 | Tela de sensores com o selo (#36, Front #13) |
| Backup do banco sem restauração testada | Cloud / R8 | Testar e documentar a restauração do backup periódico do Cosmos DB | | 27/11 | Procedimento documentado (#36) |
| Compose não testado | Cloud (final) | Validar `infra/docker-compose.yml` na máquina da equipe (custo mensal já estimado em `infra/README.md`) | | 28/11 | `docker-compose.yml`; estimativa em `infra/README.md` (#31) |
| ZAP ativo e limites restantes | Segurança | Varredura ativa (full scan) em ambiente de teste; limite em `POST /empresas` e `POST /senha` (política de privacidade já publicada) | | 25/11 | Relatório ZAP (#32) |
| Modelo de IA ainda não usa o sensor, sem `/predict` | IA | Cruzar leituras do sensor com o modelo, publicar `/predict` e mostrar no painel (modelo, baseline e model card já existem) | | 28/11 | Rota `/predict` e card no painel (#37) |
| Pesquisa só secundária e simulada | Consumidor | Validar persona e jornada (`docs/ux/`) com ≥ 5 entrevistas ou ≥ 20 respostas reais | | 25/11 | Registro da pesquisa (#38) |
| Sem alertas push e estado offline no app | UE Mobile (final) | Push por limiar e faixa "sem conexão" no PWA | | 28/11 | Demonstração no celular (Front #13) |
| Sem teste de usabilidade | UE Mobile / Consumidor (final) | Teste com 5 usuários e SUS | | 28/11 | Relatório SUS ≥ 68 (#38) |
| README `.md` e vídeo em inglês | Tech English | OpenAPI e slides do pitch já em inglês (`docs/slides/`); falta README `.md` em inglês e vídeo de até 5 min (roteiro em `docs/pitch-en.md`) | | 25/11 | Itens publicados (#33) |
| Base de ≥ 48 h e segundo sensor | IoT / Dados | Base e estatística já em `analise/sensor/` (8,5 h reais); deixar a placa coletando ≥ 48 h seguidas e regerar; confirmar sensores | | 25/11 | CSV e relatório (#39) |
| Cobertura do painel e PRs revisados | Qualidade (final) | Mínimo de cobertura já no CI do painel (29,7% de linhas); subir até 60% e ter revisão de PRs por outro membro | | 28/11 | CI com mínimo; PRs com aprovação (Front #12) |
| Deploy ainda parte da `everson` | Cloud / Qualidade | Publicar a partir da `main` e proteger a branch | | 28/11 | Workflow na `main` (#40) |
