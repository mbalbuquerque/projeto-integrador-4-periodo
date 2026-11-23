# Resiliência do ColdTrack

Estado em 23/11/2026. Os requisitos R1 a R8 seguem a tabela da prévia técnica; os testes F1 a F6
são os provocados pela banca. "Implementado" descreve o código; "Testado" só é marcado quando o
resultado foi observado e registrado aqui.

## Requisitos

| ID | Requisito | Situação | Como é feito |
|---|---|---|---|
| R1 | Reconexão automática | Implementado | A cada ciclo o laço principal testa o Wi-Fi e chama `conectarWiFi()` (até 20 tentativas por chamada, sem travar o laço); o motivo da queda é registrado (`aoCairWiFi`). O MQTT reconecta com espera de 5 s dobrando até 60 s |
| R2 | Armazenar e reenviar | Implementado | Fila em flash (`/fila.jsonl`, LittleFS), até 500 leituras (~2 h 45 min a cada 20 s). Reenvia até 10 por ciclo, mantendo o horário da medição |
| R3 | Identidade da mensagem | Implementado | Cada leitura leva `deviceId`, `medidoEm` (UTC por NTP) e `seq` (número de sequência guardado em Preferences, sobrevive ao reinício e vai na fila). A API aceita `seq`, responde `duplicada: true` no reenvio idêntico e 409 em conflito; `GET /leituras` aponta lacunas na sequência, calculadas pelo número de `seq`. Testado no Wokwi e na placa física no F1 de 17/11 (`seq` 89 a 128 contínua, `lacunas: []`) |
| R4 | Watchdog e reinício | Implementado (simulador) | Watchdog de tarefa de 60 s, alimentado nas esperas de rede e antes de cada envio. No Wokwi, um travamento provocado foi detectado pelo watchdog, a placa reiniciou e a numeração seguiu de onde parou (5 → 6). Falta a placa física |
| R5 | Falha de sensor | Implementado | Checksum do DHT validado, duas tentativas; leitura inválida não é enviada como válida. O RSSI inválido segue como `null` |
| R6 | Degradação controlada | Implementado | O dashboard mostra "Sem dados desde HH:MM" quando a última leitura tem mais de 2 min ou a API não responde, e avisa que os valores são os últimos recebidos. A validar em F4 e F6 na entrega final |
| R7 | Observabilidade | Implementado | `GET /api/health` (200/503); `online` e `ultimoContato` por sensor na API e selo Online/Offline com último contato na tela de sensores. A leitura a cada 20 s funciona como sinal de vida (sensor calado aparece offline). Com o sensor em falha, a placa (a partir do firmware 2026.11.17.2) envia `POST /api/heartbeat` a cada 20 s: a API atualiza o último contato e marca `sensor: falha` com `sensorFalhaDesde`, sem gravar leitura, e o painel mostra o aviso. Testado no Wokwi e na placa física (F3, 17/11) |
| R8 | Recuperação na nuvem | Parcial | Contêiner com health check e reinício automático validado no CI (queda do processo: volta em 4,4 s). Backup lógico (`infra/backup/`) com exportação e restauração testadas no CI contra o emulador, com dados sintéticos, e procedimento de recuperação em `infra/README.md`. O backup periódico gerenciado do Cosmos só restaura por chamado ao suporte e não foi testado; o export real de produção (23/11, 16.105 documentos) foi conferido e ensaiado em memória com `infra/backup/verificar_export.py` (contagens iguais, restauração idempotente), mas a restauração num Cosmos de verdade (emulador ou conta de teste) não foi executada |

## Testes de falha

| Teste | Critério | Situação |
|---|---|---|
| F1 Queda de rede (60 s) | Reconecta em até 30 s; sem lacuna na sequência | Aprovado na placa física (17/11) |
| F3 Falha de sensor | Leitura marcada inválida, alerta visível, nada gravado como válido | Aprovado na placa física (17/11) |
| F2 Queda de energia | Volta a enviar em até 60 s, sem perder a sequência | Aprovado na placa física (17/11) |
| F4 Serviço em nuvem fora (30 s) | Serviço volta sozinho; dispositivo retém e reenvia; zero perda | Parcial: lado da nuvem aprovado em 23/11 (a API voltou a responder 200 em 20,6 s depois do `start`); retenção e reenvio pela placa seguem pendentes, pois a placa está desligada (issue de F4 na placa) |
| F5 Mensagem duplicada | Apenas 1 registro no banco | Aprovado: reenvio idêntico responde `duplicada: true` e não grava de novo (placa física em 17/11; testes `test_telemetria_duplicada_reenvio_identico` e `test_reenvio_igual` passando em 23/11) |
| F6 ThingSpeak indisponível | O fluxo pela API continua e o painel segue atualizado | **Parcial.** Execução real (chave inválida no canal com a placa ligada) pendente (#123). Verificado sem a placa: a Function App não referencia o ThingSpeak em nenhum módulo (teste `cloud/function/test_independencia_thingspeak.py`); a placa envia à API por HTTPS e publica no ThingSpeak por MQTT depois, com falha do MQTT só adiando a próxima tentativa (`garantirMqtt`, `coldtrack.ino`); o painel lê a API em tudo (`src/lib/api.js`, `src/lib/leituras.js`, `Dashboard.jsx` a cada 20 s) e só a tela Monitoramento consulta o ThingSpeak, onde a falha do canal mostra "indisponível" sem valor antigo (`Monitoramento.test.jsx`, caso "falha do canal") e não afeta as outras telas |

Resultados de cada teste (data, procedimento, tempo medido) são anotados abaixo.

### Registro

| Teste | Data | Procedimento | Resultado medido |
|---|---|---|---|
| F1 | 17/11/2026 | Placa física (ESP32-C3, firmware 2026.11.16.2) no hotspot de celular "AAA" (2.4 GHz, WPA2/WPA3); hotspot desligado às 00:31:07 e religado após cerca de 2,5 min; log serial com horário | Queda detectada em 00:31:07; leituras `seq` 120 a 125 guardadas na fila em flash; reconectada às 00:34:07, menos de 30 s após a rede voltar; as 6 leituras foram reenviadas em ordem em 35 s; `GET /api/leituras` com `seq` 89 a 128 contínua e `lacunas: []` |
| F3 | 17/11/2026 | Placa física (ESP32-C3 + DHT11, firmware 2026.11.17.3) na rede da casa; um fio do DHT desconectado com a placa ligada por cerca de 2 min e reconectado no mesmo pino; log serial com horário | Falha detectada no primeiro ciclo após o desconecte (17:42:55): `ERRO: Falha na leitura do sensor!`, LED em `falha_sensor` e `POST /api/heartbeat` com `motivo: sensor_falha`, respondido `200` com `sensor: "falha"` e `sensorFalhaDesde` (campo que o painel usa para o aviso). Durante a falha, 6 heartbeats a cada 20 s e nenhuma leitura gravada (`seq` parado em 2732). Sensor reconectado: primeira leitura válida às 17:44:54 (`seq` 2733, sem salto), gravada no Azure às 17:44:58, recuperação no ciclo seguinte (até 20 s) |
| F2 | 17/11/2026 | Placa física (firmware 2026.11.17.3) na rede da casa; alimentação cortada ao trocar o cabo USB do computador por uma fonte (duração do corte não cronometrada, troca rápida); conferido em `GET /api/leituras` | Última leitura antes do corte: `seq` 3338, medida às 21:10:17; primeira depois do reinício: `seq` 3339, medida às 21:10:41 e gravada às 21:10:45 (24 s entre as medições, dentro dos 60 s); `lacunas: []` na última hora. O travamento com watchdog na placa física continua não executado |

### F4 na nuvem (23/11/2026)

Procedimento: `az functionapp stop` na `func-coldtrack-7319` (grupo `rg-coldtrack`), 30 s parada, depois `az functionapp start`; `GET /api/health` consultado a cada 6 s. A placa estava desligada (última leitura em 20/11 08:10 UTC), então este teste cobre só a nuvem.

| Momento (UTC) | Evento | `GET /api/health` |
|---|---|---|
| 13:53:15 | antes do teste | 200 |
| 13:53:30 | `stop` concluído | 403 (aplicativo parado) em 13:53:31, 37, 43, 49 e 55 |
| 13:54:02 | `start` pedido (30 s depois) | 403 |
| 13:54:15 | iniciando | sem resposta (conexão recusada) |
| 13:54:22 | | **200** |

Tempo de recuperação medido: **20,6 s** entre o pedido de `start` e o primeiro 200. O critério completo de F4 (a placa reter e reenviar sem perda) continua pendente de execução na placa física. Neste teste a parada foi comandada por nós; queda por falha do processo e reinício automático estão em `infra/README.md` (4,4 s no CI).

## Números medidos (coleta real de 17/11 06:46 a 20/11 08:10 UTC)

Fonte: leituras gravadas no Cosmos DB pela placa física (`analise/sensor/relatorio_cosmos.md`, gerado por `descrever_cosmos.py`). Não é um teste controlado de 24 h seguidas: é a coleta contínua da placa, com as paradas dela.

| Medida | Resultado | Meta |
|---|---|---|
| Período | 73,4 h (11.710 leituras gravadas) | 24 h ou mais |
| Taxa de perda (números de `seq` que faltam na faixa 308 a 12118) | 101 de 11.811 = **0,86%** | no máximo 1% |
| Disponibilidade (leituras gravadas ÷ esperadas a cada 20 s) | 11.710 ÷ 13.212 = **88,6%** | medir e explicar |
| Maior trecho contínuo | 10,3 h (14,0 h com tolerância de 60 s) | n/a |
| Maiores lacunas | 286,7 min (19/11 11:08 a 15:55), 21,4 min (18/11), 19,9 min (19/11), 8 min (17/11) | explicar |
| Recuperação em F1 | reconectada em menos de 30 s depois da volta da rede (17/11) | até 30 s |
| Recuperação em F2 | 24 s entre a última medição antes do corte e a primeira depois (17/11) | até 60 s |
| Recuperação em F3 | até 20 s depois do sensor reconectado (17/11) | n/a |
| Recuperação em F4 (nuvem) | 20,6 s depois do `start` (23/11) | volta sozinho |

A perda mede o que a placa numerou e a API não recebeu; o tempo com a placa desligada ou sem rede não gera `seq` e entra na disponibilidade, não na perda. A causa das lacunas não consta nos dados.

### Medições de campo adicionais (23/11/2026, sem a placa ligada)

Fonte e método em `analise/sensor/relatorio_campo.md` (script `medir_campo.py`, a partir do mesmo export de `leituras`). Só dado gravado; nenhuma medição ao vivo.

| Medida | Resultado | Meta |
|---|---|---|
| Perda em 24 h (50 janelas deslizantes de 24 h, passo 1 h, pela `seq`) | melhor 0,00%; mediana 1,12%; pior 1,96%; **23 de 50 janelas ficam em até 1%** | no máximo 1% em 24 h |
| Onde está a perda | um único buraco de **63 leituras** (18/11 17:18 a 17:39 UTC) responde por 62,4% das 101 faltantes; o resto são 31 buracos de 1 a 4 leituras, 26 deles (33 leituras) em 20/11 entre 04:31 e 05:11 UTC | explicar |
| Latência placa → banco, tempo real (10.692 leituras com atraso < 60 s) | mediana 3,9 s; p95 7,8 s; p99 19,1 s; máximo 58,8 s | até 2 intervalos de envio (40 s) |
| Reenvio de buffer (R2) em campo | 1.018 leituras (8,7%) entregues com atraso ≥ 60 s, em 21 reenvios, todos com `seq` consecutivo e na ordem da medição; o maior: 641 leituras (`seq` 6352 a 6992), medidas entre 17:39 e 21:46 UTC de 18/11 e entregues até 21:47, com atraso máximo de 166,9 min | guardar e reenviar em ordem |
| Última etapa, banco → tela | o painel consulta a API a cada 20 s (`UPDATE_INTERVAL`, `config.js`; `usePolling` no `Dashboard.jsx`): de 0 a 20 s | n/a |
| Latência ponta a ponta, **estimada** (composição, não medida) | espera pela próxima leitura (até 20 s) + upload (mediana 3,9 s, p95 7,8 s) + painel (até 20 s): típico em torno de 24 s e no pior caso cerca de 48 s | até 2 intervalos de envio (40 s); acima disso, explicar |

Leitura honesta: a perda de 24 h **não é sempre ≤ 1%**. Metade das janelas passa da meta por causa de dois episódios (o buraco de 63 leituras em 18/11 e a instabilidade de 20/11 de madrugada), em que a placa numerou leituras que não chegaram ao banco. O dado não registra a causa; é o ponto a investigar antes de 30/11 e a medição de 24 h seguidas com a placa ligada continua pendente (#125).

**Não medido** (depende da placa ligada): latência ao vivo com estímulo (#126), watchdog travando na placa física (#124), F4 com retenção e reenvio pela placa (#121) e F6 real (#123).
