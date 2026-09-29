# ColdTrack — Guia de Implantação

Passo a passo para colocar uma transportadora nova em operação: do acesso ao painel até o
sensor enviando dados do caminhão. No piloto a implantação é **assistida**: a equipe ColdTrack
grava e instala o dispositivo junto com o cliente. Cada transportadora tem a própria conta
no painel e só enxerga os próprios sensores, veículos e leituras.

Visão técnica do sistema: [`stack-tecnica.md`](stack-tecnica.md).

## 1. Papéis

| Papel | Quem | O que faz |
|---|---|---|
| Equipe técnica ColdTrack | Integrantes do projeto | Grava o firmware, instala e valida |
| Gestor do cliente | Responsável na transportadora | Cadastra a empresa, conecta sensores pelo cabo, cadastra veículos, viagens e operadores; acompanha alertas |
| Operador logístico | Equipe do cliente | Acompanha a carga no painel durante as viagens |

## 2. Checklist de material

| Item | Observação |
|---|---|
| ESP32-C3 | Um por baú |
| Sensor DHT11 (ou DHT22) | Ligado ao GPIO 4 |
| 3 LEDs + 3 resistores de 220 Ω | Verde (GPIO 5), amarelo (GPIO 6), vermelho (GPIO 7) |
| Cabo USB de dados | Para gravar o firmware e configurar o sensor pelo painel |
| Conexão | Rede Wi-Fi de 2.4 GHz (roteador do local ou hotspot do celular) |
| Alimentação | USB 5 V; no caminhão, adaptador veicular 12 V → 5 V |
| Gabinete | Com aberturas de ventilação junto ao sensor |

## 3. Passo a passo

### Passo 1 — Cadastrar a empresa

1. O gestor do cliente abre o painel e clica em **Cadastre sua empresa** (tela de login).
2. Informa o nome da empresa, o próprio nome, o e-mail e uma senha (mínimo 8 caracteres).
3. Entra direto como **gestor** da empresa, com o painel vazio e só com os dados dela.

### Passo 2 — Gravar o firmware (uma vez por placa)

A placa sai da gravação **sem rede e sem chave**: Wi-Fi, ID e chave chegam depois, pelo cabo,
no passo 3. Só é preciso gravar de novo quando o firmware mudar.

1. Copiar para uma pasta chamada `sketch` os arquivos `sketch.ino`, `azure_ca.h` e
   `secrets.example.h` do repositório. Renomear `secrets.example.h` para `secrets.h`.
2. No `secrets.h`, apagar as linhas `WIFI_*`, `DEVICE_ID` e `DEVICE_KEY` (sem elas a placa
   espera a configuração pelo cabo) e descomentar `#define DHT_TYPE DHT11` quando o sensor
   for o DHT11. O `secrets.h` **nunca** vai para o repositório (está no `.gitignore`).

**Pela Arduino IDE**

1. Em *Preferências*, adicionar o endereço de placas
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`.
2. *Gerenciador de Placas*: instalar **esp32** (Espressif).
3. *Gerenciador de Bibliotecas*: instalar **DHT sensor library** e **Adafruit Unified Sensor**.
4. Placa: **ESP32C3 Dev Module**. Em placas com USB nativo (sem chip conversor, como a
   ESP32-C3 SuperMini), ativar **USB CDC On Boot: Enabled**. Sem isso o painel não enxerga
   o sensor pelo cabo.
5. Abrir a pasta `sketch`, selecionar a porta COM do ESP32 e clicar em **Carregar**.
6. **Fechar a Arduino IDE** (ou o monitor serial) antes do passo 3: a porta só abre em um
   programa por vez.

**Pelo terminal (arduino-cli)**

```
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc sketch
arduino-cli upload  --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc -p COM5 sketch
```

Placa gravada e sem configuração: o LED amarelo pisca, esperando o cabo.

### Passo 3 — Conectar o sensor pelo cabo

Feito pelo gestor, no **Chrome ou Edge, no computador** (o navegador conversa com a placa
pelo USB; celular, Firefox e Safari não têm esse recurso).

1. Ligar a rede que o sensor vai usar na banda de **2.4 GHz** (hotspot do celular: no iPhone,
   "Maximizar compatibilidade"). O ESP32-C3 não enxerga redes de 5 GHz.
2. Ligar o sensor no computador pelo cabo USB.
3. No painel: **Sensores → Conectar sensor pelo cabo** e escolher a porta do sensor.
4. O painel mostra o ID do sensor, tirado do próprio chip (`coldtrack-` + final do endereço
   MAC). Informar uma descrição, o nome e a senha da rede e clicar em **Conectar sensor**.
5. O painel registra o sensor na empresa, gera a chave e grava rede, ID e chave na placa. A
   placa **testa a rede antes de gravar**: se a senha estiver errada ou a rede não aparecer, a
   tela diz qual foi o problema e nada é gravado.
6. Em até 1 minuto o sensor aparece **ONLINE** com a temperatura. Pode tirar do cabo e ligar
   em qualquer fonte USB: ele lembra da rede.

A senha do Wi-Fi vai só para a placa, pelo cabo: não passa pela API nem fica no navegador. A
chave vale só para aquele ID e não serve para gravar dados em nome de outro sensor.

**Trocar de rede** (de casa para o hotspot, por exemplo): ligar o sensor no cabo e repetir o
passo 3. O painel reconhece o sensor e pede só a rede nova; a chave continua a mesma.

**Simulador Wokwi / sem cabo**: **Sensores → Registrar sem cabo** gera o ID e a chave para
colar no `secrets.h` (`DEVICE_ID`, `DEVICE_KEY`, `WIFI_SSID`, `WIFI_PASSWORD`). A configuração
salva pelo cabo vale mais que o `secrets.h`.

### Passo 4 — Validar na bancada

Em **Sensores**, a tabela se atualiza sozinha a cada 20 s e mostra a situação de cada sensor
(**ONLINE**, **SEM SINAL HÁ …** ou **NUNCA ENVIOU**), o sinal Wi-Fi e a última temperatura.

Para acompanhar por dentro, abrir o monitor serial (115200 baud) **depois** de fechar o painel
(a porta só abre em um programa por vez). Em até 1 minuto devem aparecer:

| Mensagem esperada | Significa |
|---|---|
| `SENSOR: coldtrack-… \| firmware …` | Identidade carregada da placa |
| `Wi-Fi conectado!` | Rede e senha corretas |
| `Azure: gravado. Resposta: {…}` | Leitura aceita pela API e gravada no banco |
| `FAIXA: nova faixa da carga …` | Faixa do perfil da carga recebida (depois do passo 5, se o perfil não for o demonstrativo) |

Validar também:

1. **LED**: o verde acende com a carga dentro da faixa do perfil (até 15 °C no demonstrativo;
   10 a 13 °C na manga).
2. **Queda de conexão**: desligar o Wi-Fi por 1 minuto e religar. Em Sensores o sensor passa
   para **SEM SINAL** e volta para **ONLINE**; as leituras do intervalo chegam depois (ficam
   guardadas na placa).

### Passo 5 — Cadastrar o veículo

No painel, como gestor: **Veículos → Cadastrar veículo**, com o código do caminhão (ex.:
`CT-002`), o tipo, o **sensor** conectado no passo 3 (a lista mostra só os sensores livres) e o
**perfil da carga** (manga, uva ou demonstrativo). Em até 1 minuto o cartão do veículo mostra a
temperatura atual, e o sensor passa a usar a faixa daquela carga nos LEDs.

Ainda em Veículos, **Etiqueta QR** gera uma etiqueta para imprimir e colar no baú: o QR abre o
painel direto naquele veículo (quem escaneia precisa estar logado).

### Passo 6 — Instalar no baú

| Cuidado | Por quê |
|---|---|
| Sensor dentro do compartimento da carga, longe da saída direta do evaporador | Medir o ar que envolve a fruta, não o ar recém-resfriado |
| Altura intermediária, protegido de impacto dos paletes | Leitura representativa e sem dano na carga e descarga |
| Aberturas do gabinete livres | O sensor precisa de circulação de ar |
| Cabo de alimentação preso e protegido | Evitar desconexão com a vibração |
| LEDs visíveis ao abrir a porta | Conferência rápida pelo motorista |
| Etiqueta QR do lado de fora do baú | Conferência da temperatura pelo celular sem abrir a porta |

Depois de instalado, fechar o baú e confirmar no painel que as leituras continuam chegando.

### Passo 7 — Entregar a operação ao cliente

O gestor do cliente:

1. Cria os operadores em **Configurações → Usuários** (perfil Operador logístico). Cada pessoa
   troca a própria senha em **Configurações → Minha conta**.
2. Registra cada viagem em **Viagens → Registrar viagem** (veículo, origem, destino, carga e
   início) e encerra ao chegar.
3. Acompanha **Alertas** e exporta **Relatórios** em CSV por período.
4. Antes de liberar uma saída, confere **Calor na rota** no dashboard: horas acima de 30 °C
   previstas entre Petrolina e Suape e a janela mais fresca para carregar.

## 4. Sinais e solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| LED vermelho dá uma piscada a cada 20 s e nenhum outro acende | Falha na leitura do sensor | Conferir ligação do DHT (VCC, GND, dados no GPIO 4) e o `DHT_TYPE` |
| Painel: nenhum sensor aparece em **Conectar sensor pelo cabo** | Cabo só de carga, porta em uso ou firmware sem **USB CDC On Boot** | Trocar o cabo, fechar a Arduino IDE/monitor serial, regravar com a opção ligada |
| Painel: `Senha errada` / `não achou a rede` | Senha ou nome errados, ou rede em 5 GHz | Conferir e tentar de novo; deixar o hotspot em 2.4 GHz |
| LED amarelo piscando sem parar | Placa sem configuração | Fazer o passo 3 |
| Serial: `Falha na conexão Wi-Fi.` | Rede fora do alcance ou com outra senha | Aproximar da rede ou refazer o passo 3 |
| Serial: `Azure: erro HTTP 401` | Sensor removido ou chave trocada | Conectar pelo cabo e marcar **Gerar chave nova e gravar no sensor** |
| Serial: `Azure: erro HTTP 400` | Leitura recusada pela validação | A resposta lista o motivo; conferir sensor e relógio |
| Serial: `FILA: sem relogio sincronizado` | Horário ainda não obtido pela internet | Aguardar alguns segundos após conectar |
| Painel: veículo **SEM SINAL** | Sem leitura há mais de 1 minuto | Conferir alimentação e conexão do dispositivo |
| Painel pede login de novo | Sessão venceu (8 horas) ou a senha foi trocada | Entrar novamente |
| Login: `muitas tentativas erradas` | 5 senhas erradas seguidas | Esperar 15 minutos ou pedir ao gestor para **Redefinir senha** |
| Veículos: `Nenhum sensor livre` | Todos os sensores já estão em veículos | Conectar outro sensor em Sensores |

## 5. Encerrar um cliente ou trocar um dispositivo

- **Trocar dispositivo**: o ESP32 novo tem outro ID (vem do chip). Conectar pelo cabo e trocar
  o sensor do veículo em **Veículos**; o histórico do anterior continua no banco.
  Dispositivo perdido ou roubado: **Gerar nova chave** ou **Remover** em Sensores.
- **Retirar veículo**: gestor remove em **Veículos**; as leituras já gravadas continuam no banco.
- **Remover sensor**: só depois de retirar o veículo que o usa.
- **Remover acesso**: gestor remove o usuário em **Configurações → Usuários**; a sessão dele
  cai na hora.

## 6. Evolução prevista

| Hoje (piloto) | Versão comercial |
|---|---|
| Configuração pelo cabo USB, no computador | Configuração pelo celular, por Bluetooth |
| Placa gravada pela equipe | Placa entregue já gravada |
| Faixas de manga e uva de referência | Faixas validadas com o produtor |
