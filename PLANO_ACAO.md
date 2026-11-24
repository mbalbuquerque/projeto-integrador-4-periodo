# Plano de ação

Criado em 16/11/2026 a partir da matriz `REQUISITOS_UC.md` e do `RESILIENCIA.md`; revisado em
23/11/2026 (aula de ajustes). Cada linha tem uma issue; as que dependem da placa física levam
"(placa)" no responsável. Entrega final: tag `v1.0` antes da aula de 30/11.

## Pendências até 30/11

| Lacuna | UC / critério | Ação concreta | Responsável | Prazo | Evidência de conclusão |
|---|---|---|---|---|---|
| Latência P1 a P6 sem medição | IoT / Integração | Medido com ventilador em 24/11: 3 estímulos, 1 com efeito visível, causa do > 40 s explicada. Repetir com objeto frio para chegar a 5 degraus claros | Everson (placa) | 27/11 | Tabela em `docs/qa/relatorio-de-testes.md` (#126) |
| Sem calibração (**Lacuna justificada**, #128) | IoT / Placa | Não calibrado: a equipe não teve termômetro de referência antes de 30/11; a precisão do datasheet do DHT11 é de ±2 °C. Desde o firmware 2026.11.23.1 cada leitura guarda o valor bruto (`temperaturaBruta`/`umidadeBruta`), então uma correção pode ser aplicada depois sem perder o histórico. Próximo passo: comparar em 3 pontos contra uma referência e registrar em `docs/calibracao.md` | Everson (placa) | depois de 30/11 | `docs/calibracao.md` (#128) |
| Sem caixa adequada | IoT / Placa | Acomodar o artefato em caixa adequada | Everson (placa) | 28/11 | Foto da caixa (#129), `docs/hardware/caixa.md` |
| Modelo do sensor não supera o baseline (**Lacuna justificada**, #37) | IA | Re-treinado em 24/11 com a base de 17/11 a 24/11 (Cosmos, 71 h de amostras, incluindo a excursão provocada em bancada de 23-24/11): ridge MAE 0,383 °C contra 0,364 °C da persistência no teste temporal; na janela da excursão, 1,608 contra 1,496 °C. LAD e gradient boosting também não passaram. A excursão caiu inteira no teste, então o treino segue sem subida ou descida forte para aprender. A rota recomenda o baseline e o painel exibe a previsão. Justificativa: reavaliado em 24/11 (PR #171), a rota recomenda a persistência e o painel a exibe, e o model card explica. Próximo passo: coletar excursões em dias diferentes (caixa refrigerada real), algumas no período de treino | Everson | 30/11 | Model card e `relatorio_previsao.md` (#37) |
| Banco sem diagrama ER e script | IoT / Banco | Diagrama, script de criação e dados de exemplo para o Cosmos | Everson | 27/11 | `docs/` e `infra/` (#130) |
| Estrutura e README finais | Cloud / Tech English | Mapa de pastas, usuário de teste e passos de execução | Everson | 28/11 | README em português e inglês (#132) |
| Revisão de PRs | Qualidade | Everson é o revisor designado da equipe e revisa os PRs antes do merge a partir de 23/11 (regra em `CONTRIBUTING.md`); os PRs anteriores foram mergeados sem revisão formal | Everson | 30/11 | Regra em `CONTRIBUTING.md` |
| Fichas e relatórios de qualidade | Segurança / Qualidade | Ficha OWASP IoT e API, relatório ISO/IEC 25010 e análise estática limpa | Everson | 28/11 | #134, #135, #136 |
| Firmware final e API completa | IoT / Cloud | Filtro de leitura e parâmetros fora do código; CRUD com paginação e TLS no envio | Everson | 28/11 | #137, #139 |
| Limpeza dos dados | IoT / Dados | Limpeza documentada e base que alimenta o modelo | Everson | 27/11 | `analise/sensor/` (#138) |
| Projeto de Segurança (2FA, IDOR, evidências) | Segurança | Issues do Emmanuel e do Enzo; tag `entrega-final` | Emmanuel e Enzo | 23/11 23h59 | #112 a #115 |
| PDF de entrega, apresentação e tag | Todas | Gerar o PDF de entrega e os slides; criar a tag `v1.0` antes da aula | Everson | 30/11 | #140, #141 |

## Decisões da equipe

- Pesquisa com usuários: mantida simulada e declarada como tal (`docs/ux/respostas-pesquisa-simulada.md`), sem coleta real. O SUS simulado (média 73,5) não vale como teste de usabilidade.
- Vídeo de até 5 min em inglês: descartado. Seguem o `README.en.md`, a OpenAPI em inglês, os slides e o roteiro `docs/pitch-en.md`.
- Base de 48 h: lida como 48 h de coleta somadas (69,0 h no ThingSpeak; 73,4 h de período no Cosmos). Não há trecho contínuo de 48 h; o maior tem 10,3 h.

## Concluídas

| Lacuna | Evidência |
|---|---|
| F1, F2 e F3 na placa física (17/11) | `RESILIENCIA.md` (#34) |
| F4 na nuvem (23/11) | `RESILIENCIA.md`: API volta a responder em 20,6 s |
| F4 na placa física (24/11) | `RESILIENCIA.md` (#121): serviço voltou em 20 s, a placa reteve e reenviou em ordem, zero leitura perdida, sem duplicado |
| F6 na placa física (24/11) | `RESILIENCIA.md` (#123): MQTT do ThingSpeak falhando, `seq` 12509 a 12519 gravadas na API a cada ~20 s sem lacuna; canal sem entrada de 02:11:08 a 02:17:15 UTC |
| Watchdog na placa física (R4, 24/11) | `RESILIENCIA.md` (#124): reinício 60,3 s depois do travamento, `seq` 12519 → 12520 sem lacuna, primeira leitura gravada 89 s depois do comando |
| F5 mensagem duplicada | `duplicada: true` na placa em 17/11; testes automatizados (#122) |
| Perda, disponibilidade e recuperação medidas | Perda 0,86% e disponibilidade 88,6% em 73,4 h; `RESILIENCIA.md` e `analise/sensor/relatorio_cosmos.md` (#125) |
| Base de ≥ 48 h de coleta | `analise/sensor/relatorio.md` e `relatorio_cosmos.md` (#39) |
| Sequência validada só no simulador (R3) | F1 na placa física em 17/11: `seq` 89 a 128 contínua e `lacunas: []` |
| Heartbeat do firmware (R7) | `POST /api/heartbeat` e aviso no painel |
| Backup do banco (R8) | Backup lógico com restauração testada no CI (`infra/backup/`, #36); export real de produção (16.105 documentos) restaurado numa conta Cosmos de teste em 23/11, contagens iguais (#131) |
| Limites de requisição | `POST /empresas` e `POST /senha` com testes de 429 |
| Alertas push | Web Push na API (`/api/push/*`) e no painel |
| Deploy pela `main` | Os dois workflows publicam a cada push na `main` (#40) |
| Cobertura | 99,8% no back-end e 99,2% no painel; mínimo de 98% no CI |