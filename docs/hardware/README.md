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

O firmware aplica uma mediana de `FILTRO_JANELA` leituras válidas (padrão 5, valores de 3 a 9;
1 desliga) à temperatura e à umidade antes de classificar e enviar. Leitura inválida (checksum
ruim ou NAN) nunca entra na janela e continua indo para o fluxo de falha de sensor (R5). Com
leitura a cada 20 s, a mediana de 5 atrasa uma mudança real em cerca de 40 s e elimina picos
isolados. O parâmetro se troca no `secrets.h` (ver `secrets.example.h`).

Validação: testes unitários C++ (`firmware/tests/test_firmware.cpp`, rodam no CI) e compilação
do firmware no CI. **Validação na placa física: pendente** (conferir no monitor serial que um
pico induzido, como soprar no sensor por uma leitura, não chega ao painel como valor isolado).
