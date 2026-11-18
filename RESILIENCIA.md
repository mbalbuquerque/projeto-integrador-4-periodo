# Resiliência do ColdTrack

Estado em 17/11/2026. Os requisitos R1 a R8 seguem a tabela da prévia técnica; os testes F1 a F6
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
| R8 | Recuperação na nuvem | Parcial | Contêiner com health check e reinício automático validado no CI (queda do processo: volta em 4,4 s). Backup lógico (`infra/backup/`) com exportação e restauração testadas no CI contra o emulador, com dados sintéticos, e procedimento de recuperação em `infra/README.md`. O backup periódico gerenciado do Cosmos só restaura por chamado ao suporte e não foi testado; a restauração de um export real de produção não foi executada |

## Testes de falha

| Teste | Critério | Situação |
|---|---|---|
| F1 Queda de rede (60 s) | Reconecta em até 30 s; sem lacuna na sequência | Aprovado na placa física (17/11) |
| F3 Falha de sensor | Leitura marcada inválida, alerta visível, nada gravado como válido | Aprovado na placa física (17/11) |
| F2 Queda de energia | Volta a enviar em até 60 s, sem perder a sequência | Aprovado na placa física (17/11) |
| F4, F5, F6 | Ver prévia técnica | F5 observado na placa física (reenvio após timeout respondido como `duplicada: true`); F4 e F6 na entrega final |

Resultados de F1 e F3 (data, procedimento, tempo medido) devem ser anotados abaixo depois da
execução. Enquanto estiverem em branco, valem como não evidenciados.

### Registro

| Teste | Data | Procedimento | Resultado medido |
|---|---|---|---|
| F1 | 17/11/2026 | Placa física (ESP32-C3, firmware 2026.11.16.2) no hotspot de celular "AAA" (2.4 GHz, WPA2/WPA3); hotspot desligado às 00:31:07 e religado após cerca de 2,5 min; log serial com horário | Queda detectada em 00:31:07; leituras `seq` 120 a 125 guardadas na fila em flash; reconectada às 00:34:07, menos de 30 s após a rede voltar; as 6 leituras foram reenviadas em ordem em 35 s; `GET /api/leituras` com `seq` 89 a 128 contínua e `lacunas: []` |
| F3 | 17/11/2026 | Placa física (ESP32-C3 + DHT11, firmware 2026.11.17.3) na rede da casa; um fio do DHT desconectado com a placa ligada por cerca de 2 min e reconectado no mesmo pino; log serial com horário | Falha detectada no primeiro ciclo após o desconecte (17:42:55): `ERRO: Falha na leitura do sensor!`, LED em `falha_sensor` e `POST /api/heartbeat` com `motivo: sensor_falha`, respondido `200` com `sensor: "falha"` e `sensorFalhaDesde` (campo que o painel usa para o aviso). Durante a falha, 6 heartbeats a cada 20 s e nenhuma leitura gravada (`seq` parado em 2732). Sensor reconectado: primeira leitura válida às 17:44:54 (`seq` 2733, sem salto), gravada no Azure às 17:44:58, recuperação no ciclo seguinte (até 20 s) |
| F2 | 17/11/2026 | Placa física (firmware 2026.11.17.3) na rede da casa; alimentação cortada ao trocar o cabo USB do computador por uma fonte (duração do corte não cronometrada, troca rápida); conferido em `GET /api/leituras` | Última leitura antes do corte: `seq` 3338, medida às 21:10:17; primeira depois do reinício: `seq` 3339, medida às 21:10:41 e gravada às 21:10:45 (24 s entre as medições, dentro dos 60 s); `lacunas: []` na última hora. O travamento com watchdog na placa física continua não executado |
