# Hardware do ColdTrack

Lista de componentes, esquema elétrico, pinagem e segurança do envio. Complementa
`firmware/wokwi/diagram.json` (simulação) e `docs/como-funciona.md`.
Pendências físicas (calibração e caixa) estão em [`calibracao.md`](calibracao.md) e
[`caixa.md`](caixa.md).

## Lista de componentes (BOM)

| Qtd | Componente | Onde | Observação |
|---|---|---|---|
| 1 | ESP32-C3 (DevKitM-1 no Wokwi; placa física com OLED 0,42" embutido) | nó sensor | Wi-Fi 2,4 GHz; firmware em `firmware/coldtrack/` |
| 1 | Sensor DHT11 (placa física) ou DHT22 (Wokwi) | GPIO 4 | temperatura (°C) e umidade (%); DHT11 não mede abaixo de 0 °C |
| 1 | Tela OLED SSD1306 72x40 (embutida na placa física) | GPIO 5 (SDA) e 6 (SCL) | só com `TELA_OLED` no `secrets.h` |
| 3 | LED (verde, amarelo, vermelho) | GPIO 5, 6 e 7 | só no Wokwi (sem `TELA_OLED`) |
| 3 | Resistor 220 Ω | em série com cada LED | só no Wokwi |
| 1 | Fonte USB 5 V (cabo USB-C) | alimentação | o mesmo cabo grava o firmware e configura Wi-Fi, ID e chave |
| 1 | Caixa de proteção | ver [`caixa.md`](caixa.md) | pendente |

Conferido contra `firmware/wokwi/diagram.json` (1 placa, 1 DHT22, 3 LEDs, 3 resistores) e
`firmware/wokwi/indicadores/tela/diagram.json` (placa, DHT22, botão que simula a falha do fio,
OLED SSD1306). Na placa física o sensor é um DHT11; o firmware escolhe o tipo por `DHT_TYPE`
no `secrets.h` (padrão DHT22).

## Pinagem real do firmware

| Função | GPIO | Definição no código |
|---|---|---|
| Dados do DHT (open-drain, pull-up interno) | 4 | `DHT_PIN` (`coldtrack.ino`) |
| I2C da tela, SDA | 5 | `TELA_SDA` |
| I2C da tela, SCL | 6 | `TELA_SCL` |
| LED verde / amarelo / vermelho (Wokwi) | 5 / 6 / 7 | `diagram.json` (a tela ocupa 5 e 6 na placa física) |
| LED da placa (opcional) | 8 (simples) ou 2 (RGB) | `LED_PLACA` no `secrets.h` |
| Alimentação do DHT | 3V3 | fio vermelho no `diagram.json` |
| Terra comum | GND | fio preto |

## Esquema elétrico

- Simulação: abrir `firmware/wokwi/diagram.json` no Wokwi (esquema principal) e
  `firmware/wokwi/indicadores/tela/diagram.json` (versão com tela).
- Ligação do sensor (igual na placa física): DHT VCC → 3V3; DHT GND → GND; DHT dados → GPIO 4.
  O firmware liga o pull-up interno; com fio longo ou módulo sem resistor, usar 10 kΩ entre
  dados e 3V3.

## Segurança do envio (TLS)

Verificado em `firmware/coldtrack/coldtrack.ino` (firmware 2026.11.17.4):

- Telemetria e heartbeat: `HTTPClient` sobre `WiFiClientSecure` com `setCACert(AZURE_ROOT_CA)`
  (linhas 1229 e 1314), URL `https://func-coldtrack-7319.azurewebsites.net/api/...`.
- MQTT: `clienteMqtt.setCACert(AZURE_ROOT_CA)` (linha 1416).
- Não há `setInsecure()`: o certificado do servidor é validado contra a CA raiz embutida em
  `firmware/coldtrack/azure_ca.h`. Segredos (Wi-Fi, ID e chave do sensor) ficam em `secrets.h`
  (fora do Git) ou na memória da placa.
- Limite conhecido: quem tem a placa na mão pode ler a chave gravada nela (ver `docs/stride.md`).

## Filtro de mediana nas leituras

O firmware aplica uma mediana das últimas leituras válidas (janela padrão 5, valores aceitos 1
ou 3 a 9; 1 desliga) à temperatura e à umidade antes de classificar e enviar. Leitura inválida
(checksum ruim ou NAN) nunca entra na janela e continua indo para o fluxo de falha de sensor
(R5). Com leitura a cada 20 s, a mediana de 5 atrasa uma mudança real em cerca de 40 s e
elimina picos isolados.

**Valor bruto preservado.** O payload leva o valor filtrado em `temperatura`/`umidade` e a
leitura do sensor antes do filtro em `temperaturaBruta`/`umidadeBruta`. A API valida os dois
na mesma faixa física e grava os brutos junto da leitura no Cosmos, só para auditoria: status,
alertas e painel usam o valor filtrado. Firmware antigo (sem os campos) continua aceito.

## Comandos pelo cabo USB

Monitor serial a 115200, uma linha por comando terminada em Enter ("Nova linha"). A placa responde
numa linha que começa com `CT>`; o resto da serial é log. Abrir a porta pode reiniciar a placa:
espere `CT>{"pronto":true,"fw":".."}` antes de digitar.

| comando | o que faz | resposta |
|---|---|---|
| `CT<{"cmd":"info"}` | identidade, rede e versão do firmware | `CT>{"id":..,"chip":..,"configurado":..,"ssid":..,"wifi":..,"fw":..}` |
| `CT<{"cmd":"redes"}` | redes 2,4 GHz que a placa vê | `CT>{"ok":true,"redes":[..]}` |
| `CT<{"cmd":"wifi","ssid":"..","senha":".."}` | troca a rede (testa antes de gravar) | `CT>{"ok":true,"wifi":"conectado",..}` |
| `CT<{"cmd":"config","ssid":"..","senha":"..","id":"..","chave":".."}` | rede e identidade do sensor | idem |
| `CT<{"cmd":"parametros","intervalo":20000,"filtroJanela":5}` | parâmetros de coleta (abaixo) | `CT>{"ok":true,"intervalo":..,"filtroJanela":..}` |
| `CT<{"cmd":"teste","acao":"travar"}` | **teste R4**: trava o laço; o watchdog reinicia a placa em 60 s | `CT>{"ok":true,"teste":"travar","seq":..,"ms":..,"watchdogS":60}` |
| `CT<{"cmd":"teste","acao":"thingspeak_invalido"}` | **teste F6**: MQTT com senha inválida, só na memória; a API segue | `CT>{"ok":true,"teste":"thingspeak_invalido","ms":..}` |
| `CT<{"cmd":"teste","acao":"normal"}` | desfaz o `thingspeak_invalido` sem reiniciar | `CT>{"ok":true,"teste":"normal","ms":..}` |

Os comandos `teste` são só para os testes de resiliência: não gravam nada na flash (um reinício
desfaz) e não mostram credenciais. Ação desconhecida responde
`CT>{"ok":false,"erro":"acao_desconhecida"}`; firmware compilado sem MQTT responde
`CT>{"ok":false,"erro":"sem_mqtt"}` às ações do ThingSpeak. O passo a passo, com o que anotar,
está em [`RESILIENCIA.md`](../../RESILIENCIA.md), seção "Roteiros na placa física".

## Parâmetros de coleta (fora do código)

Intervalo entre leituras e janela do filtro ficam na flash da placa (Preferences, namespace
`config`, chaves `intervalo` e `janela`) e são lidos no boot. Valor ausente ou fora da regra
volta ao padrão de fábrica do `payload_core.h`.

| parâmetro | padrão | faixa aceita | por quê |
|---|---|---|---|
| intervalo (`intervalo`, ms) | 20000 | 15000 a 300000 | mínimo de 15 s do ThingSpeak gratuito; acima de 5 min o painel já trata o sensor como sem leitura recente |
| janela do filtro (`filtroJanela`) | 5 | 1 (desliga) ou 3 a 9 | 5 leituras descartam um pico isolado com atraso de ~2 intervalos |

Troca pelo cabo USB (monitor serial a 115200, linha terminada em Enter):

```
CT<{"cmd":"parametros","intervalo":30000,"filtroJanela":3}
CT>{"ok":true,"intervalo":30000,"filtroJanela":3}
```

Os dois campos são opcionais; `CT<{"cmd":"parametros"}` só consulta os valores em uso. A placa
valida tudo antes de gravar (tudo ou nada) e recusa com
`CT>{"ok":false,"erro":"intervalo_invalido"|"janela_invalida","intervalo":..,"filtroJanela":..}`,
sempre devolvendo os valores que continuam valendo. Aplica sem reiniciar: a janela nova começa
vazia e o próximo ciclo sai um intervalo novo depois do comando. O padrão de fábrica ainda pode
ser trocado na compilação (`FILTRO_JANELA` e `INTERVALO_ENVIO_PADRAO_MS` no `secrets.h`), mas
o que estiver gravado na placa vale mais.

**Limites de temperatura (faixas):** não ficam no firmware. A faixa de cada carga (mínimo,
máximo e margem) vem da nuvem na resposta de `POST /api/telemetria`, conforme o perfil do
veículo, e a placa guarda a última recebida na flash (namespace `coldtrack`) para o LED e a
tela seguirem funcionando sem rede. Mudar a faixa é cadastro no painel, não firmware.

Validação: testes unitários C++ (`firmware/tests/test_firmware.cpp`: filtro com janela
configurada, valor bruto no payload, faixas aceitas, leitura da flash e o comando
`parametros`), testes de contrato e de rota da API (`test_contrato.py`, `test_rotas.py`) e
compilação do firmware no CI. **Validação na placa física: pendente** (conferir no monitor
serial que um pico induzido, como soprar no sensor por uma leitura, não chega ao painel como
valor isolado, que `temperaturaBruta` mostra o pico, e que o comando `parametros` sobrevive a
um reinício da placa).
