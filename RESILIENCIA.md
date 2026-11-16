# Resiliência do ColdTrack

Estado em 16/11/2026. Os requisitos R1 a R8 seguem a tabela da prévia técnica; os testes F1 a F6
são os provocados pela banca. "Implementado" descreve o código; "Testado" só é marcado quando o
resultado foi observado e registrado aqui.

## Requisitos

| ID | Requisito | Situação | Como é feito |
|---|---|---|---|
| R1 | Reconexão automática | Implementado | A cada ciclo o laço principal testa o Wi-Fi e chama `conectarWiFi()` (até 20 tentativas por chamada, sem travar o laço); o motivo da queda é registrado (`aoCairWiFi`). O MQTT reconecta com espera de 5 s dobrando até 60 s |
| R2 | Armazenar e reenviar | Implementado | Fila em flash (`/fila.jsonl`, LittleFS), até 500 leituras (~2 h 45 min a cada 20 s). Reenvia até 10 por ciclo, mantendo o horário da medição |
| R3 | Identidade da mensagem | Parcial | Cada leitura leva `deviceId` e `medidoEm` (UTC por NTP). A API grava com id derivado dos dois e responde `duplicada: true` num reenvio idêntico; valores diferentes no mesmo horário dão 409. Não há número de sequência |
| R4 | Watchdog e reinício | Pendente | Sem watchdog de tarefa configurado no firmware |
| R5 | Falha de sensor | Implementado | Checksum do DHT validado, duas tentativas; leitura inválida não é enviada como válida. O RSSI inválido segue como `null` |
| R6 | Degradação controlada | Implementado | O dashboard mostra "Sem dados desde HH:MM" quando a última leitura tem mais de 2 min ou a API não responde, e avisa que os valores são os últimos recebidos. A validar em F4 e F6 na entrega final |
| R7 | Observabilidade | Parcial | `GET /api/health` (200/503); `GET /api/dispositivos` devolve `ultimoContato` e `online` (última leitura há no máximo 120 s) por sensor. Falta mostrar o selo online/offline na tela de sensores e um heartbeat próprio do firmware (hoje a própria leitura faz esse papel) |
| R8 | Recuperação na nuvem | Parcial | Cosmos DB com backup periódico (`backupPolicy: Periodic` no Bicep); falta testar e documentar uma restauração. Contêiner com reinício automático e verificação de saúde em `infra/docker-compose.yml` (não testado ainda) |

## Testes de falha

| Teste | Critério | Situação |
|---|---|---|
| F1 Queda de rede (60 s) | Reconecta em até 30 s; sem lacuna na sequência | A executar e registrar |
| F3 Falha de sensor | Leitura marcada inválida, alerta visível, nada gravado como válido | A executar e registrar |
| F2, F4, F5, F6 | Ver prévia técnica | Entrega final |

Resultados de F1 e F3 (data, procedimento, tempo medido) devem ser anotados abaixo depois da
execução. Enquanto estiverem em branco, valem como não evidenciados.

### Registro

| Teste | Data | Procedimento | Resultado medido |
|---|---|---|---|
| F1 | | | |
| F3 | | | |
