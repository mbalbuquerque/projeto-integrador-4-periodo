# Resiliência do ColdTrack

Estado em 23/11/2026. Os requisitos R1 a R8 seguem a tabela da prévia técnica; os testes F1 a F6
são os provocados pela banca. "Implementado" descreve o código; "Testado" só é marcado quando o
resultado foi observado e registrado aqui.

## Requisitos

| ID | Requisito | Situação | Como é feito |
|---|---|---|---|
| R1 | Reconexão automática | Implementado | A cada ciclo o laço principal testa o Wi-Fi e chama `conectarWiFi()` (até 20 tentativas por chamada, sem travar o laço); o motivo da queda é registrado (`aoCairWiFi`). O MQTT reconecta com espera de 20 s dobrando até 60 s |
| R2 | Armazenar e reenviar | Implementado | Fila em flash (`/fila.jsonl`, LittleFS), até 500 leituras (~2 h 45 min a cada 20 s). Reenvia até 10 por ciclo, mantendo o horário da medição |
| R3 | Identidade da mensagem | Implementado | Cada leitura leva `deviceId`, `medidoEm` (UTC por NTP) e `seq` (número de sequência guardado em Preferences, sobrevive ao reinício e vai na fila). A API aceita `seq`, responde `duplicada: true` no reenvio idêntico e 409 em conflito; `GET /leituras` aponta lacunas na sequência, calculadas pelo número de `seq`. Testado no Wokwi e na placa física no F1 de 17/11 (`seq` 89 a 128 contínua, `lacunas: []`) |
| R4 | Watchdog e reinício | Implementado (simulador) | Watchdog de tarefa de 60 s, alimentado nas esperas de rede e antes de cada envio. No Wokwi, um travamento provocado foi detectado pelo watchdog, a placa reiniciou e a numeração seguiu de onde parou (5 → 6). Falta a placa física |
| R5 | Falha de sensor | Implementado | Checksum do DHT validado, duas tentativas; leitura inválida não é enviada como válida. O RSSI inválido segue como `null` |
| R6 | Degradação controlada | Implementado | O dashboard mostra "Sem dados desde HH:MM" quando a última leitura tem mais de 2 min ou a API não responde, e avisa que os valores são os últimos recebidos. A validar em F4 e F6 na entrega final |
| R7 | Observabilidade | Implementado | `GET /api/health` (200/503); `online` e `ultimoContato` por sensor na API e selo Online/Offline com último contato na tela de sensores. A leitura a cada 20 s funciona como sinal de vida (sensor calado aparece offline). Com o sensor em falha, a placa (a partir do firmware 2026.11.17.2) envia `POST /api/heartbeat` a cada 20 s: a API atualiza o último contato e marca `sensor: falha` com `sensorFalhaDesde`, sem gravar leitura, e o painel mostra o aviso. Testado no Wokwi e na placa física (F3, 17/11) |
| R8 | Recuperação na nuvem | Atendido | Contêiner com health check e reinício automático validado no CI (queda do processo: volta em 4,4 s). Backup lógico (`infra/backup/`) com exportação e restauração testadas no CI contra o emulador, com dados sintéticos, e procedimento de recuperação em `infra/README.md`. O backup periódico gerenciado do Cosmos só restaura por chamado ao suporte e não foi testado; o export real de produção (23/11/2026, 16.105 documentos) foi conferido com `infra/backup/verificar_export.py` e restaurado de verdade numa conta Cosmos de teste, com contagens iguais em todos os containers (leituras 16.100, empresas 3, veículos 1, dispositivos 1, viagens 0), em 782 s; a conta de teste foi apagada e a produção não foi tocada |

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

### F4 com a placa ligada (24/11/2026)

Procedimento igual ao de 23/11 (`az functionapp stop`, 30 s, `az functionapp start`, `GET /api/health` a cada ~5 s), agora com a placa `coldtrack-0e0b2c` enviando a cada 20 s (firmware em uso na placa, anterior a 2026.11.23.1). Sequência conferida no Cosmos (`leituras`, campo `seq`).

| Momento (UTC) | Evento |
|---|---|
| 00:33:26 | `GET /api/health` 200; última leitura em tempo real: seq 12229 (medida 00:32:22) |
| 00:33:38 | `stop` concluído; health 403/sem resposta até o `start` |
| 00:34:10 | `start` pedido |
| 00:34:31 | **health 200** (recuperação: 21 s depois do `start`) |
| 00:34:54 a 00:36:01 | placa reenvia o buffer: seq 12231 a 12236, atrasos de 64 s a 13 s, em ordem |
| 00:36:14 | volta ao tempo real (atraso ~5 s) |

**Resultado: reprovado por 1 leitura.** O serviço voltou sozinho e a placa reteve e reenviou o que mediu, mas a seq **12230** se perdeu. Causa: o App Service parado responde **HTTP 403**, e o firmware tratava todo 4xx como dado recusado pelo contrato e descartava a leitura (`falhaTemporaria` só guardava erro de rede e 5xx). Pelo mesmo motivo, 32 leituras foram descartadas com **401** entre 00:20 e 00:31 de 24/11, quando a chave do sensor foi cadastrada de novo no painel e a placa ainda usava a antiga.

**Correção (firmware 2026.11.23.1, PR #165):** só o dado recusado pelo contrato (400, 409, 413, 422) é descartado; 401, 403, 404, 408, 429, 5xx e falha de rede ficam na fila e são reenviados. Teste `falhaTemporaria guarda na fila tudo menos dado recusado` em `firmware/tests/test_firmware.cpp`. Falta gravar o firmware novo na placa e repetir o F4.

Observação: durante a parada o ThingSpeak também ficou sem dado (00:32:32 a 00:34:27), porque a mesma tarefa de envio espera o timeout da API antes de publicar no canal. Isso é registrado em F6/R6.

## Roteiros na placa física (R4 e F6, firmware 2026.11.24.1)

Os dois testes se fazem só com o cabo USB e um monitor serial, sem recompilar: grave o firmware
2026.11.24.1 (ou mais novo) e abra o Monitor Serial do Arduino IDE (ou outro terminal) em
**115200**, com fim de linha **"Nova linha"** (ou "Ambos NL e CR"). Abrir a porta pode reiniciar a
placa: espere a linha `CT>{"pronto":true,"fw":"2026.11.24.1"}` antes de digitar. Cada comando é
uma linha inteira, colada exatamente como está abaixo, seguida de Enter. Os comandos de teste não
gravam nada na flash, não mostram senha nem chave, e um reinício desfaz qualquer um deles.

Para conferir a sequência no banco: `GET /api/leituras` do sensor (ou a tela de leituras do
painel), olhando o campo `seq` e a lista `lacunas`.

### R4: watchdog na placa física (#124)

O watchdog vigia o laço principal (a tarefa que mede e lê o cabo) com prazo de 60 s. O comando
trava esse laço de propósito, sem alimentar o watchdog; a tarefa de envio continua mandando o que
já estava na fila.

1. Com a placa enviando normalmente (linhas `MEDIDA;https;...;1` a cada 20 s), anote o horário.
2. Digite:

   ```
   CT<{"cmd":"teste","acao":"travar"}
   ```

3. Resposta esperada, na hora (os números são de exemplo):

   ```
   CT>{"ok":true,"teste":"travar","seq":12345,"ms":456789,"watchdogS":60}
   TESTE: loop travado de proposito em millis=456789, ultima seq=12345. O watchdog deve reiniciar a placa em 60 s.
   ```

   Anote o **horário** e a **`seq`** dessa linha (última leitura numerada antes do travamento).
   A tela e o LED ficam parados; é o esperado.
4. Cerca de 60 s depois aparece `task_wdt: Task watchdog got triggered` citando `loopTask`, e a
   placa reinicia sozinha (o monitor serial pode desconectar e reconectar a porta). Anote o
   horário do reinício.
5. No boot, confira as linhas `SEQ: ultima leitura numerada <N>` e `WATCHDOG: placa reiniciada por
   travamento; retomando fila e sequencia.` A tela mostra `REINICIO WDT` por cerca de 1 min.
6. Anote a `seq` da primeira leitura depois do reinício e o horário em que ela foi gravada
   (`MEDIDA;https;...;1`).

**Aprovado se:** a placa reiniciou sozinha (sem tirar o cabo), a primeira `seq` depois do boot é a
anotada no passo 3 mais 1 e `lacunas` fica vazia no intervalo. Registrar: horário do comando,
horário do reinício (esperado ~60 s depois), `seq` antes e depois, horário da primeira leitura
gravada depois do boot (tempo total de recuperação). O comando não se repete sozinho depois do
reinício.

### F6: ThingSpeak indisponível para a placa (#123)

O comando faz o MQTT da placa conectar ao ThingSpeak com uma senha inválida, só na memória. O
broker recusa a conexão (como se o canal estivesse indisponível) e o envio à API segue igual.
O que este teste prova: o fluxo placa → API → painel não depende do ThingSpeak. Ele não derruba a
leitura do canal pela tela Monitoramento (essa falha já é coberta pelo teste do painel).

1. Com a placa enviando normalmente, confira no log `MQTT: publicado field1=...` a cada ciclo e
   anote a última `seq` e o horário.
2. Digite:

   ```
   CT<{"cmd":"teste","acao":"thingspeak_invalido"}
   ```

   Resposta: `CT>{"ok":true,"teste":"thingspeak_invalido","ms":...}` e
   `TESTE: MQTT com senha invalida (so na RAM); a API segue normal.` Anote o horário.
3. No ciclo seguinte aparecem `MQTT: conectando ao ThingSpeak (TESTE: senha invalida)...`,
   `MQTT: falhou (...)` com o motivo (esperado 4, usuário/senha errados, ou 5, sem autorização) e
   `MEDIDA;mqtt-conexao;<ms>;...;0`. Anote esse `<ms>` (quanto a tentativa recusada levou).
   Depois disso a placa tenta de novo com espera de 20 s, 40 s e 60 s, sem parar o envio à API.
4. Deixe assim por **pelo menos 3 minutos** (9 ciclos). Durante esse tempo devem continuar as
   linhas `MEDIDA;https;...;1` a cada ~20 s, o Dashboard do painel segue atualizando e o canal do
   ThingSpeak não recebe nada novo.
5. Digite:

   ```
   CT<{"cmd":"teste","acao":"normal"}
   ```

   Resposta: `CT>{"ok":true,"teste":"normal","ms":...}`. No ciclo seguinte: `MQTT: conectado.` e
   `MQTT: publicado ...`. Anote o horário da primeira publicação.

**Aprovado se:** nenhuma leitura deixou de chegar à API no período (`seq` contínua, `lacunas`
vazia) e o intervalo entre leituras gravadas ficou em ~20 s, como antes do teste. Registrar: horário
de início e fim, `seq` no início e no fim, o `<ms>` das tentativas recusadas, o maior intervalo
entre duas leituras gravadas no período, e o tempo até o ThingSpeak voltar a receber depois do
`normal`. Se a placa reiniciar no meio, o MQTT volta sozinho à senha certa.

Por que o MQTT recusado não atrasa a API: a publicação roda na tarefa de envio **depois** do envio
à API. Uma tentativa de conexão que falha custa no máximo ~14 s (3 s de TCP, 8 s de TLS, 3 s de
resposta do broker; com senha errada o broker recusa bem antes) e a próxima só sai 20 s depois,
dobrando até 60 s, então no máximo um ciclo em dois tenta e o envio do ciclo seguinte não fica
para trás (firmware 2026.11.24.1; antes eram 4 s de TCP, 5 s de resposta e espera a partir de 5 s,
o que permitia uma tentativa lenta a cada ciclo). O inverso, a API fora do ar segurando o
ThingSpeak (visto em 24/11), continua como descrito em F4.

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

Latência ao vivo com estímulo (ventilador, 24/11, #126): ver `docs/qa/relatorio-de-testes.md`. Três estímulos, só um com efeito visível (t_banco 41 s, painel ≤ 61 s, com t0 aproximado); placa → banco na sessão com mediana 4,65 s e p95 26,3 s, sem buraco de `seq`. Repetir com objeto frio para fechar as 5 medições.

**Não medido** (depende da placa ligada): watchdog travando na placa física (#124), F4 com retenção e reenvio pela placa (#121) e F6 real (#123). Os roteiros de R4 e F6 com o cabo USB estão em "Roteiros na placa física".
