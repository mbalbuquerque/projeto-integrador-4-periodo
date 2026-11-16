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
| R6 | Degradação controlada | Pendente | O painel não mostra "sem dados desde HH:MM" |
| R7 | Observabilidade | Parcial | Há RSSI e horário da leitura; faltam rota `/health` e heartbeat com status online/offline |
| R8 | Recuperação na nuvem | Pendente | Sem backup do Cosmos DB com restauração testada |

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
