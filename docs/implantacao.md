# ColdTrack — Guia de Implantação

Passo a passo para colocar uma transportadora nova em operação: do acesso ao painel até o
sensor enviando dados do caminhão. No piloto a implantação é **assistida**: a equipe ColdTrack
prepara o dispositivo e entrega o acesso pronto ao cliente.

Visão técnica do sistema: [`stack-tecnica.md`](stack-tecnica.md).

## 1. Papéis

| Papel | Quem | O que faz |
|---|---|---|
| Equipe técnica ColdTrack | Integrantes do projeto | Cria o gestor do cliente, grava o firmware, instala e valida |
| Gestor do cliente | Responsável na transportadora | Cadastra veículos, viagens e operadores; acompanha alertas |
| Operador logístico | Equipe do cliente | Acompanha a carga no painel durante as viagens |

## 2. Checklist de material

| Item | Observação |
|---|---|
| ESP32-C3 | Um por baú |
| Sensor DHT11 (ou DHT22) | Ligado ao GPIO 4 |
| 3 LEDs + 3 resistores de 220 Ω | Verde (GPIO 5), amarelo (GPIO 6), vermelho (GPIO 7) |
| Cabo USB | Para gravar o firmware |
| Conexão | Wi-Fi no piloto; módulo 4G com chip na versão final |
| Alimentação | USB 5 V; no caminhão, adaptador veicular 12 V → 5 V |
| Gabinete | Com aberturas de ventilação junto ao sensor |

## 3. Passo a passo

### Passo 1 — Criar o acesso do gestor do cliente

1. Entrar no painel com uma conta de gestor da equipe ColdTrack.
2. **Configurações → Usuários → Criar usuário**: nome, e-mail do gestor do cliente, perfil
   **Gestor** e uma senha inicial (mínimo 8 caracteres).
3. Enviar ao cliente o endereço do painel, o e-mail e a senha inicial por um canal privado.

### Passo 2 — Definir a identificação do dispositivo

Cada sensor tem um **ID único** usado no banco e no painel. Padrão: `coldtrack-NN`
(`coldtrack-02`, `coldtrack-03`, …). Anotar o ID numa etiqueta presa ao gabinete.

### Passo 3 — Preparar o firmware

1. Copiar para uma pasta chamada `sketch` os arquivos `sketch.ino`, `azure_ca.h` e
   `secrets.example.h` do repositório. Renomear `secrets.example.h` para `secrets.h`.
2. Preencher o `secrets.h`:

| Campo | Valor |
|---|---|
| `WIFI_SSID` / `WIFI_PASSWORD` | Rede Wi-Fi disponível para o dispositivo |
| `DHT_TYPE` | Descomentar `#define DHT_TYPE DHT11` quando o sensor for o DHT11 |
| `AZURE_FUNCTION_URL` | Já preenchido com o endereço da API |
| `AZURE_FUNCTION_KEY` | Chave de dispositivo, obtida pela equipe técnica (ver abaixo) |

3. No `sketch.ino`, trocar `#define DEVICE_ID "coldtrack-01"` pelo ID definido no passo 2.

A chave de dispositivo é consultada por quem tem acesso ao Azure do projeto:

```
az functionapp keys list -n func-coldtrack-7319 -g rg-coldtrack --query functionKeys.default -o tsv
```

O `secrets.h` **nunca** vai para o repositório (está no `.gitignore`).

### Passo 4 — Gravar o ESP32-C3

**Pela Arduino IDE**

1. Em *Preferências*, adicionar o endereço de placas
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`.
2. *Gerenciador de Placas*: instalar **esp32** (Espressif).
3. *Gerenciador de Bibliotecas*: instalar **DHT sensor library** e **Adafruit Unified Sensor**.
4. Placa: **ESP32C3 Dev Module**. Em placas com USB nativo (sem chip conversor, como a
   ESP32-C3 SuperMini), ativar **USB CDC On Boot: Enabled** para ver o monitor serial.
5. Abrir a pasta `sketch`, selecionar a porta COM do ESP32 e clicar em **Carregar**.

**Pelo terminal (arduino-cli)**

```
arduino-cli compile --fqbn esp32:esp32:esp32c3 sketch
arduino-cli upload  --fqbn esp32:esp32:esp32c3 -p COM5 sketch
arduino-cli monitor -p COM5 -c baudrate=115200
```

### Passo 5 — Validar na bancada

Com o monitor serial aberto (115200 baud), em até 1 minuto devem aparecer:

| Mensagem esperada | Significa |
|---|---|
| `Wi-Fi conectado!` | Rede e senha corretas |
| `Payload JSON: {"deviceId":"coldtrack-NN",…}` | Sensor lido e JSON montado |
| `Azure: gravado. Resposta: {…}` | Leitura aceita pela API e gravada no banco |

Validar também:

1. **LED**: o verde acende com a carga em temperatura normal (até 15 °C no perfil demonstrativo).
2. **Queda de conexão**: desligar o Wi-Fi por 1 minuto e religar. O serial deve mostrar
   `FILA: leitura guardada offline` e depois `FILA: N reenviadas`.

### Passo 6 — Cadastrar o veículo

No painel, como gestor: **Veículos → Cadastrar veículo**, com o código do caminhão (ex.:
`CT-002`), o tipo, o **ID do sensor** do passo 2 e o perfil da carga. Em até 1 minuto o
cartão do veículo mostra a temperatura atual e a situação da carga.

### Passo 7 — Instalar no baú

| Cuidado | Por quê |
|---|---|
| Sensor dentro do compartimento da carga, longe da saída direta do evaporador | Medir o ar que envolve a fruta, não o ar recém-resfriado |
| Altura intermediária, protegido de impacto dos paletes | Leitura representativa e sem dano na carga e descarga |
| Aberturas do gabinete livres | O sensor precisa de circulação de ar |
| Cabo de alimentação preso e protegido | Evitar desconexão com a vibração |
| LEDs visíveis ao abrir a porta | Conferência rápida pelo motorista |

Depois de instalado, fechar o baú e confirmar no painel que as leituras continuam chegando.

### Passo 8 — Entregar a operação ao cliente

O gestor do cliente:

1. Cria os operadores em **Configurações → Usuários** (perfil Operador logístico).
2. Registra cada viagem em **Viagens → Registrar viagem** (veículo, origem, destino, carga e
   início) e encerra ao chegar.
3. Acompanha **Alertas** e exporta **Relatórios** em CSV por período.

## 4. Sinais e solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| LED vermelho dá uma piscada a cada 20 s e nenhum outro acende | Falha na leitura do sensor | Conferir ligação do DHT (VCC, GND, dados no GPIO 4) e o `DHT_TYPE` |
| Serial: `Falha na conexão Wi-Fi.` | Rede ou senha erradas, ou sem sinal | Conferir o `secrets.h` e a cobertura |
| Serial: `Azure: erro HTTP 401` | Chave de dispositivo errada | Conferir `AZURE_FUNCTION_KEY` |
| Serial: `Azure: erro HTTP 400` | Leitura recusada pela validação | A resposta lista o motivo; conferir sensor e relógio |
| Serial: `FILA: sem relogio sincronizado` | Horário ainda não obtido pela internet | Aguardar alguns segundos após conectar |
| Painel: veículo **SEM SINAL** | Sem leitura há mais de 1 minuto | Conferir alimentação e conexão do dispositivo |
| Painel pede login de novo | Sessão venceu (8 horas) | Entrar novamente |

## 5. Encerrar um cliente ou trocar um dispositivo

- **Trocar dispositivo**: gravar o novo ESP32 com o mesmo ID; o histórico continua.
- **Retirar veículo**: gestor remove em **Veículos**; as leituras já gravadas continuam no banco.
- **Remover acesso**: gestor remove o usuário em **Configurações → Usuários**.

## 6. Evolução prevista

| Hoje (piloto) | Versão comercial |
|---|---|
| Implantação assistida pela equipe | Cadastro da empresa pelo próprio cliente, com dados separados por empresa |
| Wi-Fi e ID definidos no código | Configuração pelo celular e registro do dispositivo por QR code |
| Mesma chave para todos os dispositivos | Chave própria por dispositivo |
| Wi-Fi | Módulo 4G com chip e GPS |
