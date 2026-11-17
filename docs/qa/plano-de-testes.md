# Plano de testes do ColdTrack

Plano de testes formal (requisito QS-03), no formato enxuto da IEEE 829 e da ISO/IEC/IEEE 29119-3.
Versão de 16/11/2026, para a prévia técnica do PI. Os números citados foram medidos nesta data,
exceto onde a seção diz o contrário. O plano não substitui os relatórios de execução; ele define
o que se testa, como, em que ambiente e quando o resultado vale.

Documentos relacionados:

- [`metricas-de-qualidade.md`](metricas-de-qualidade.md): métricas coletadas em 10/11/2026.
- `Front-End-pi/docs/relatorio-de-testes.md`: relatório de execução do painel (08/11/2026).
- [`../../RESILIENCIA.md`](../../RESILIENCIA.md): requisitos R1 a R8 e registro de F1 e F3.
- [`../roteiro-falhas.md`](../roteiro-falhas.md): roteiro de execução de F1 e F3.
- [`../relatorio-seguranca.md`](../relatorio-seguranca.md) e [`../stride.md`](../stride.md): segurança.
- [`../../REQUISITOS_UC.md`](../../REQUISITOS_UC.md): matriz de requisitos das UCs.

## 1. Escopo

Verificar que o ColdTrack, do sensor ao painel, mede, transmite, armazena e exibe a temperatura e
a umidade da carga com as garantias prometidas: dados corretos, isolamento entre empresas,
autenticação e autorização, e comportamento controlado diante de falhas de rede, de sensor e de
nuvem.

Dentro do escopo: firmware do ESP32-C3, API (Azure Functions + Cosmos DB), painel web/PWA,
infraestrutura como código e pipelines de CI.

Fora do escopo desta versão:

- teste de carga e de estresse (não há meta de vazão definida);
- teste de invasão manual (a varredura é passiva);
- tela e rota do motorista (em desenvolvimento por outro integrante; entram na próxima revisão);
- calibração do sensor contra referência (pendência da entrega final);
- restauração do backup do Cosmos DB (R8, ainda não executada).

## 2. Itens testados

| Item | Local | Tecnologia |
|---|---|---|
| Firmware | `firmware/coldtrack/` (`coldtrack.ino`, `payload_core.h`) | C++ (Arduino/ESP32-C3), DHT11/DHT22, Wi-Fi, MQTT, fila em LittleFS |
| API | `cloud/function/` | Python 3.11, Azure Functions, Cosmos DB, JWT HS256, OpenAPI |
| Painel/PWA | repositório `Front-End-pi` | React, Vite, service worker |
| Infraestrutura | `infra/` | Bicep, Dockerfile, `docker-compose.yml`, Application Insights |
| Análise de risco térmico | `analise/` | Python (INMET 2019 a 2025) |
| Pipelines | `.github/workflows/` nos dois repositórios | GitHub Actions |

## 3. Níveis e tipos de teste

| Nível | O que verifica | Ferramenta | Onde roda | Estado em 16/11/2026 |
|---|---|---|---|---|
| Unitário (API) | Validação, classificação térmica, hash e token, limites, idempotência | pytest, unittest, Hypothesis, time-machine | CI e máquina local | 242 testes passam |
| Unitário (painel) | Bibliotecas `src/lib`, clientes da API, regras de tela | Vitest 2.1.9 (jsdom) | CI e máquina local | 163 testes em 23 arquivos passam |
| Unitário (firmware) | Montagem do payload, leitura de faixa, classificação | g++ nativo (`firmware/tests/test_firmware.cpp`) | CI | 4 funções de teste; não executadas nesta máquina (sem g++); o CI executa |
| Unitário (análise) | Limpeza e métricas do modelo | pytest | CI | 7 testes passam |
| Integração (API) | Rotas completas com Cosmos DB falso (`test_falsos.py`), sem rede | pytest | CI | Incluído nos 242 |
| Contrato OpenAPI | Spec válida, toda rota documentada e vice-versa, segurança por rota | `test_openapi.py` | CI | Incluído nos 242 |
| Pacote de publicação | Lista `pacote.txt` coerente com os módulos | `test_pacote.py` | CI | Incluído nos 242 |
| Compilação do firmware | Sketch compila para ESP32-C3 com DHT22 e DHT11 | arduino-cli | CI | Verde nas execuções recentes da `main` (consulta ao GitHub em 16/11/2026) |
| Build de contêiner | `infra/Dockerfile` constrói | `docker build` | CI | Verde nas execuções recentes da `main` (consulta ao GitHub em 16/11/2026) |
| E2E simulado | Telas e fluxos com API e terceiros interceptados | Playwright 1.64.1 (Chromium) | CI do painel | 206 passaram, 18 pulados de propósito (08/11/2026) |
| E2E contra produção | Site publicado e API real, com limpeza dos dados `QA-` | Playwright (`npm run test:e2e:real`) | Máquina local, sob demanda | 57 passaram (08/11/2026) |
| Segurança de dependências | Vulnerabilidades conhecidas | pip-audit 2.7.3, `npm audit --omit=dev --audit-level=high` | `seguranca.yml` nos dois repositórios | Sem achado (relatório de 16/11/2026) |
| Segurança dinâmica | Varredura passiva da API publicada | OWASP ZAP baseline | `seguranca.yml` | 0 alertas altos, 12 avisos triados |
| Resiliência | Falhas provocadas (F1 a F6) | Manual na placa e testes automatizados | Placa, nuvem | F5 coberto por teste; os demais pendentes (seção 8) |
| Aceitação/usabilidade | Percepção de usuários | Formulário | A coletar | Pendente (CC-01) |

Não há medição de cobertura do firmware nem do e2e. A cobertura de linhas do painel é baixa fora
de `src/lib` porque as telas são verificadas por e2e, que o Vitest não conta (ver
`metricas-de-qualidade.md`, seção 2).

## 4. Ambientes

| Ambiente | Descrição | Uso |
|---|---|---|
| Local | Windows 10, Python 3.10.11, Node.js 24; Cosmos DB falso, sem rede | Desenvolvimento e verificação antes do push |
| CI | GitHub Actions, `ubuntu-latest`, Python 3.11, Node.js 20 | Lint, testes, build, compilação do firmware, segurança |
| Simulação | Wokwi (`firmware/wokwi/diagram.json`) | Esquema elétrico e firmware com DHT22 |
| Placa | ESP32-C3 com DHT11, Wi-Fi de bancada ou hotspot | F1, F3 e F2 |
| Produção | Azure Functions (`func-coldtrack-7319`) + Cosmos DB, site no Azure Storage | E2E real, ZAP, F4 (por contêiner) |
| Contêiner local | `infra/docker-compose.yml` | F4 (parada do contêiner) |

A suíte da API roda em Python 3.10 localmente e em 3.11 no CI; o CI é a referência. O Docker não
é usado na máquina de desenvolvimento; os casos que exigem contêiner (F4) rodam em outra máquina
da equipe. Escrita contra a API de produção só ocorre no e2e real, com dados de prefixo `QA-`
removidos ao final.

## 5. Critérios de entrada e saída

Entrada (começar uma rodada de testes):

1. Código na branch de trabalho, compilando e com lint limpo (`ruff check .`, `npm run lint`).
2. Dependências instaladas a partir dos arquivos de versão fixa (`requirements*.txt`, `package-lock.json`).
3. Para e2e real: site publicado na versão a testar e conta de demonstração disponível.
4. Para F1 a F4: placa enviando leituras e painel aberto no sensor, conforme `roteiro-falhas.md`.

Saída (a rodada vale como aprovada):

| Critério | Limite | Verificado por | Medido em 16/11/2026 |
|---|---|---|---|
| Testes da API | 0 falhas | `pytest` no CI | 242 passaram, 0 falharam |
| Cobertura da API (linhas e ramos) | mínimo de 98% (`--cov-fail-under=98`) | `pytest --cov --cov-branch` | 99,61% (1.174 instruções, 4 não cobertas; 372 ramos, 2 parciais) |
| Lint | 0 avisos | `ruff check .`, `npm run lint` | `ruff`: sem avisos |
| Testes do painel | 0 falhas | `npx vitest run` | 163 passaram, 0 falharam |
| Testes da análise | 0 falhas | `pytest ../../analise` | 7 passaram |
| E2E simulado | 0 falhas (pulados só os de projeto desktop) | `npm run test:e2e` | 0 falhas em 08/11/2026 |
| Build do painel e compilação do firmware | sem erro | CI | verde |
| Dependências | sem vulnerabilidade alta | `seguranca.yml` | sem achado |
| Defeito aberto de severidade alta | nenhum aberto | etiquetas `sev:*` | nenhum registrado como issue (ver `metricas-de-qualidade.md`) |
| Resiliência | critério de cada caso da seção 6 cumprido e registrado | `RESILIENCIA.md` | ver seção 8 |
| Perda de leituras em 24 h ou mais | no máximo 1% (meta do professor, entrega final) | contagem no banco | não medido |

Suspensão: pipeline vermelho na `main`, ou ambiente de produção indisponível (`GET /api/health` diferente de 200). Retomada: causa corrigida e rodada repetida desde a entrada.

## 6. Casos de teste de resiliência (F1 a F6)

Os critérios vêm do documento do professor (seção 4.2). Situação possível: **Automatizado**
(passa no CI), **A executar na placa** (depende de montagem física), **Final** (previsto para a
entrega de 30/11/2026). Nenhum caso manual consta como executado; o registro de F1 e F3 em
`RESILIENCIA.md` continua em branco, e por isso valem como não evidenciados.

### TC-F1 Queda de rede (60 s)

- Requisitos: R1, R2.
- Pré-condição: placa ligada, conectada ao hotspot, enviando a cada 20 s; Monitor Serial aberto; última leitura anotada.
- Passos: (1) anotar `t0` e desligar o hotspot por 60 s; (2) conferir no Serial "Wi-Fi desconectado" e as leituras indo para a fila; (3) religar o hotspot e anotar o horário de volta e o da primeira leitura reenviada; (4) consultar o histórico do sensor.
- Resultado esperado: reconexão com a rede e reenvio da fila, mantendo o `medidoEm` original de cada leitura.
- Critério: reconecta em até 30 s depois da volta da rede e não há lacuna na sequência de leituras do período no banco.
- Medidas a registrar: leituras enfileiradas, reenviadas, tempo de reconexão.
- Situação: **a executar na placa** (prévia e final).

### TC-F2 Queda de energia

- Requisitos: R4.
- Pré-condição: placa enviando e painel aberto.
- Passos: desconectar a alimentação, religar e observar o painel sem intervir.
- Resultado esperado: a placa reinicia, reconecta e volta a enviar.
- Critério: novo dado no painel em até 60 s, sem intervenção.
- Situação: **final**. O firmware não tem watchdog (R4 pendente); a fila em flash sobrevive ao reinício.

### TC-F3 Falha de sensor

- Requisitos: R5, R6.
- Pré-condição: placa enviando leituras válidas.
- Passos: (1) desconectar o fio de dados do DHT; (2) esperar dois ciclos (cerca de 40 s); (3) observar o Serial, o painel e o banco; (4) religar o fio.
- Resultado esperado: a leitura é descartada pelo checksum, nada é enviado como válido, o painel mostra o estado sem dados recentes; ao religar, as leituras voltam sozinhas.
- Critério: leitura marcada inválida, alerta visível e nenhum valor inválido gravado como válido.
- Situação: **a executar na placa** (prévia e final). A lógica de descarte (checksum e duas tentativas) está no firmware e o alerta de "sem dados" está no painel; a execução com o fio desligado ainda não foi registrada.

### TC-F4 Serviço em nuvem fora

- Requisitos: R2, R6, R8.
- Pré-condição: API em contêiner (`docker-compose.yml`), placa e painel ativos.
- Passos: parar o contêiner por 30 s e religá-lo; observar placa e painel.
- Resultado esperado: o contêiner volta sozinho (`restart: unless-stopped`, healthcheck em `/api/health`); a placa retém e reenvia; o painel avisa indisponibilidade sem travar.
- Critério: serviço volta sozinho, zero perda, painel indica indisponibilidade.
- Situação: **final**. O reinício automático ainda não foi testado na máquina da equipe (CLD-07).

### TC-F5 Mensagem duplicada

- Requisitos: R3.
- Pré-condição: leitura já gravada para o par `deviceId` + `medidoEm`.
- Passos: reenviar a mesma requisição `POST /api/telemetria`; depois reenviar o mesmo horário com valores diferentes.
- Resultado esperado: reenvio idêntico responde 200 com `duplicada: true` e não cria registro; valores diferentes no mesmo horário respondem 409.
- Critério: apenas um registro no banco.
- Evidência automatizada, em `cloud/function/`:
  - `test_rotas.py::TestTelemetria::test_telemetria_duplicada_reenvio_identico` (200 e `duplicada`);
  - `test_rotas.py::TestTelemetria::test_telemetria_conflito_valores_diferentes` (409);
  - `test_contrato.py::TestLeituraDuplicada` (id derivado de `deviceId` e `medidoEm`, e comparação dos valores).
- Situação: **automatizado** (passa em 16/11/2026). A prova de "um só registro" é a gravação com id determinístico; repetir contra o Cosmos DB real fica para a entrega final.

### TC-F6 ThingSpeak indisponível

- Requisitos: R1, R6.
- Pré-condição: placa enviando à API e ao ThingSpeak.
- Passos: usar chave inválida do ThingSpeak ou bloquear o domínio; observar o painel.
- Resultado esperado: o envio pela API continua e o painel segue atualizado.
- Critério: fluxo pela API e painel atualizados.
- Situação: **final**. O painel lê da API, não do ThingSpeak (que fica só na tela Monitoramento); falta executar com o canal bloqueado.

Medidas exigidas no relatório final (entrega de 30/11/2026): taxa de perda em pelo menos 24 h
(meta: até 1%), disponibilidade do dispositivo (heartbeats recebidos ÷ esperados) e tempo de
recuperação em F1, F2 e F4. Hoje nenhuma das três foi medida.

## 7. Casos de segurança (401, 403, 400)

Todos automatizados, em `cloud/function/`, e passam em 16/11/2026. Corpo de erro no formato
`{"erros": [...]}`.

| ID | Cenário | Esperado | Teste automatizado |
|---|---|---|---|
| TC-S01 | Rota do painel sem token | 401 | `test_rotas.py::test_leituras_sem_autorizacao`; `test_acesso.py::test_sair_sem_token` |
| TC-S02 | Token adulterado, vencido, de outro segredo ou com algoritmo `none` | rejeitado | `test_seguranca.py` (`test_token_adulterado`, `test_token_vencido`, `test_outro_segredo`, `test_algoritmo_none_rejeitado`) |
| TC-S03 | Token antigo depois de sair (sessão revogada no servidor) | 401 | `test_acesso.py::test_sair_derruba_todos_os_tokens` |
| TC-S04 | Telemetria com chave de dispositivo errada ou dispositivo inexistente | 401 | `test_rotas.py::test_telemetria_chave_errada`, `test_telemetria_dispositivo_inexistente` |
| TC-S05 | Login com e-mail inexistente e com senha errada | mesma resposta 401, sem revelar qual falhou | `test_acesso.py::test_mesma_resposta_para_inexistente_errada_e_espera` |
| TC-S06 | Operador executa ação de gestor | 403 | `test_rotas.py::test_post_dispositivo_permissao_operador_nega`; e2e real REAL-OPE-03 (12 ações) |
| TC-S07 | Usuário sem perfil | 403 | `test_acesso.py::test_cadastro_sem_perfil_nega` |
| TC-S08 | Corpo que não é JSON, campo inválido ou parâmetro ausente | 400 com erro por campo | `test_rotas.py` (`test_telemetria_corpo_invalido`, `test_login_corpo_invalido`, `test_leituras_sem_device_id`, `test_post_dispositivo_corpo_invalido`, `test_usuarios_post_corpo_invalido`) |
| TC-S09 | Acesso a item de outra empresa | 404, sem vazar existência | `test_rotas.py::test_leituras_dispositivo_de_outra_empresa`; `test_acesso.py::test_gestor_nao_redefine_de_outra_empresa` |
| TC-S10 | Tentativas de login em excesso (por conta e por IP) | espera crescente; 429 por IP | `test_acesso.py::test_espera_cresce_e_libera_com_a_senha_certa`, `test_limite_por_ip`; `test_limites.py` |
| TC-S11 | Log sem e-mail completo | e-mail mascarado | `test_acesso.py::test_log_sem_email_completo` |
| TC-S12 | Cabeçalhos de segurança nas respostas | presentes | `test_cabecalhos.py` |
| TC-S13 | Spec OpenAPI sem credencial real e com segurança por rota | válida | `test_openapi.py` |
| TC-S14 | Dependências e varredura passiva | sem alerta alto | `seguranca.yml` (pip-audit, npm audit, ZAP) |

## 8. Resultados e situação

Medido em 16/11/2026, na máquina local (Python 3.10.11), a partir da `main` do back-end e da
árvore de trabalho do painel:

| Suíte | Comando | Resultado |
|---|---|---|
| API | `cd cloud/function && python -m pytest --cov=. --cov-branch --cov-fail-under=98` | 242 passaram, 0 falharam, 29 subtestes; cobertura 99,61% |
| Lint da API | `ruff check .` | sem avisos |
| Análise | `python -m pytest analise` | 7 passaram |
| Painel | `npx vitest run` | 163 passaram em 23 arquivos |

Os 230 testes da API e os 158 do painel que aparecem em `metricas-de-qualidade.md` (10/11/2026) e
no relatório do painel (08/11/2026) são de datas anteriores; a diferença vem de testes
adicionados depois. Os números de e2e (206 simulados, 57 reais) são do relatório de 08/11/2026 e
não foram repetidos nesta data. O teste do firmware em C++ não foi executado nesta máquina.

Resumo da resiliência:

| Caso | Situação em 16/11/2026 |
|---|---|
| TC-F1 | A executar na placa; sem registro |
| TC-F2 | Final; R4 (watchdog) pendente |
| TC-F3 | A executar na placa; sem registro |
| TC-F4 | Final; reinício do contêiner não testado |
| TC-F5 | Automatizado, passa |
| TC-F6 | Final |

## 9. Rastreabilidade: requisito para teste

IDs de `REQUISITOS_UC.md` e de `RESILIENCIA.md`. "Sem teste" indica lacuna a tratar.

| Requisito | Descrição resumida | Teste ou evidência | Lacuna |
|---|---|---|---|
| IOT-02 | Esquema elétrico | Simulação Wokwi | Sem teste automatizado |
| IOT-03 | Intervalo e leitura inválida | Testes C++ do `payload_core.h`; TC-F3 | Execução na placa pendente |
| IOT-05 | Envio à API | `test_rotas.py` (telemetria); e2e real | Nenhuma para a API |
| IOT-06 | 48 h de coleta | Nenhum | Sem teste: coleta e estatística pendentes |
| CLD-01, CLD-02, CLD-08 | HTTPS, segredos, `.env.example` | `test_openapi.py::test_sem_credencial_real`; revisão de configuração | Revisão manual |
| CLD-03 | Dockerfile | Job `docker` do CI | Nenhuma |
| CLD-04 | Deploy automático | `publicar-api.yml` (testa antes de publicar) | Nenhuma |
| CLD-05 | Rota de saúde | `test_health.py` (200, 503 sem vazar erro, sem autenticação) | Nenhuma |
| CLD-06 | Logs centralizados | Revisão do `main.bicep` | Sem teste automatizado |
| CLD-07 | Reinício e healthcheck | TC-F4 | Não testado na máquina da equipe |
| SEG-01 | JWT | `test_seguranca.py` (TC-S02, TC-S03) | Nenhuma |
| SEG-02 | 401, 403, 400 | TC-S01, S04 a S08 | Nenhuma |
| SEG-03 | Isolamento por empresa | TC-S09 | Nenhuma |
| SEG-04 | STRIDE | `docs/stride.md` | Documento, sem teste |
| SEG-05 | Limite de requisições | `test_limites.py`, TC-S10 | Cobre login, chat e assistente; demais rotas sem limite |
| SEG-06 | LGPD | `docs/lgpd.md` | Documento, sem teste |
| SEG-07 | Dependências e ZAP | TC-S14 | Varredura passiva apenas |
| QS-01, QS-02 | Testes e cobertura no CI | `testes.yml`, 99,61% | Nenhuma |
| QS-03 | Plano de testes | Este documento | Execuções manuais pendentes |
| QS-04 | Registro de defeitos | Templates e etiquetas `sev:*` e `amb:*` | Nenhuma issue de bug aberta no período |
| IA-03 | Divisão temporal e métrica | `analise/test_*.py` (7 testes) | Cobertura da análise de 52,7% (10/11/2026) |
| IA-05 | `/predict` | Nenhum | Rota inexistente |
| MOB-01 | PWA autenticando e listando | e2e simulado e real (REAL-AUTH, REAL-TEL) | Execução real de 08/11/2026 |
| ENG-02 | Documentação da API em inglês | `test_openapi.py` | Nenhuma |
| R1 | Reconexão automática | TC-F1 | Execução pendente |
| R2 | Armazenar e reenviar | TC-F1, TC-F4 | Execução pendente |
| R3 | Identidade da mensagem | TC-F5, `test_contrato.py::TestLeituraDuplicada` | Sem número de sequência |
| R4 | Watchdog | TC-F2 | Requisito pendente no firmware |
| R5 | Falha de sensor | TC-F3, testes C++ | Execução pendente |
| R6 | Degradação controlada | TC-F3, TC-F4, TC-F6; e2e (estados vazio e erro) | Validar em F4 e F6 |
| R7 | Observabilidade | `test_health.py`, `test_online.py` | Selo online/offline na tela de sensores ainda não verificado |
| R8 | Recuperação na nuvem | TC-F4 | Restauração do backup não testada |

## 10. Riscos do plano

| Risco | Impacto | Mitigação |
|---|---|---|
| F1 a F4 dependem de placa, rede e contêiner na data da banca | Casos sem evidência | Ensaiar antes; contingência de roteador ou hotspot próprio |
| Testes usam Cosmos DB falso | Diferença de comportamento em produção | E2E real contra produção; F5 repetido contra o banco real na entrega final |
| Cobertura de linhas do painel baixa fora de `src/lib` | Regressão em tela sem alerta unitário | E2E simulado cobre as telas; meta de cobertura do painel a definir |
| Firmware testado em cópia das funções (`payload_core.h`) | Divergência entre o teste e o `.ino` | Incluir o header no `.ino` |
| Sensor DHT11 com precisão limitada e um só sensor (IOT-01) | Dados pouco confiáveis | Calibração documentada na entrega final |
| Horas e custo de retrabalho estimados, não apontados | Métricas imprecisas | Apontar horas daqui em diante |
| Suíte real escreve em produção | Resíduo de dados | Prefixo `QA-` e script de limpeza ao final |
| Segredo no CI ou no repositório | Vazamento | `secrets.h` fora do Git; OIDC no Azure |

## 11. Papéis

| Papel | Responsabilidade |
|---|---|
| Responsável pela qualidade | Manter este plano, os testes da API e do painel e o registro de defeitos |
| Responsável pelo firmware | Executar e registrar F1, F2 e F3 na placa; manter os testes C++ |
| Responsável pela nuvem e infraestrutura | Executar F4 e F6; testar restauração do backup; manter o CI |
| Responsável pelo painel | Manter Vitest e Playwright; executar o e2e real |
| Orientador | Define os critérios de aceitação e acompanha os testes de falha na banca |

## 12. Características da ISO/IEC 25010:2023

| Característica | Como é verificada hoje | O que falta |
|---|---|---|
| Adequação funcional | Testes de rota e de contrato (242 na API), classificação térmica, e2e simulado e real do painel | Sensor único (IOT-01); coleta de 48 h e estatística (IOT-06); `/predict` (IA-05) |
| Eficiência de desempenho | Intervalo de leitura de 20 s justificado; limites de requisição | Nenhuma medição de latência, vazão ou consumo; sem teste de carga |
| Compatibilidade | E2E em Chromium (1280 px e 390 px); PWA; spec OpenAPI validada | Outros navegadores; interoperabilidade com outros sensores |
| Interação (usabilidade) | E2E de fluxos e de responsividade; textos revisados; navegação por etiqueta QR | Pesquisa com usuários (CC-01); auditoria de acessibilidade além de verificações pontuais |
| Confiabilidade | Fila em flash e reenvio; idempotência (TC-F5); rota de saúde; reinício automático previsto | F1 a F4 e F6 sem execução registrada; sem medida de perda em 24 h ou de disponibilidade; restauração do backup; watchdog |
| Segurança | JWT com sessão revogável; 401, 403, 400, 404; isolamento por empresa; espera de login; pip-audit, npm audit e ZAP passivo; STRIDE | Teste de invasão; limites em todas as rotas; exclusão de empresa e política de privacidade (LGPD) |
| Manutenibilidade | Lint no CI; 99,61% de cobertura na API; documentação em `docs/`; CI em todo push | Cobertura do painel e do firmware; testes do firmware ligados ao `.ino` |
| Flexibilidade | Perfis de carga configuráveis (`GET /perfis`); empresa e veículo cadastráveis; infraestrutura em Bicep | Teste de implantação em outra assinatura; adaptação a outro microcontrolador não verificada |
| Safety (segurança operacional) | Classificação normal, atenção e crítico e alerta de carga fora da faixa, nos testes de contrato e do firmware; leitura inválida nunca vai como válida (R5) | Execução de F3; verificação do alerta de ponta a ponta com a carga real; análise de perigos formal |

## 13. Manutenção do plano

Atualizar este documento quando um caso de F1 a F6 for executado (registrar também em
`RESILIENCIA.md`), quando um requisito mudar de status em `REQUISITOS_UC.md` e a cada entrega.
Os números da seção 8 devem ser remedidos a cada atualização, com a data.
