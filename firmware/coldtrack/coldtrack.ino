#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <time.h>
#include "driver/gpio.h"
#include <Preferences.h>
#include <esp_task_wdt.h>
#include <esp_sntp.h>
#include "secrets.h"
#include "azure_ca.h"
// Montagem do payload, leitura de numero no JSON e classificacao da faixa:
// as mesmas funcoes que o firmware/tests/test_firmware.cpp testa no CI.
#include "payload_core.h"

// MQTT (ThingSpeak) so entra com as credenciais no secrets.h; sem elas
// (Wokwi) o firmware segue so com o HTTPS.
#if defined(MQTT_CANAL) && defined(MQTT_CLIENT_ID) && defined(MQTT_USUARIO) && defined(MQTT_SENHA)
#define COM_MQTT
#include <PubSubClient.h>
#endif


// ================= MEDICAO HTTPS x MQTT =================
//
// Cliente TLS que conta os bytes de aplicacao que passam por ele (antes da
// criptografia): o que o HTTP ou o MQTT escreveu e leu. Cada envio vira uma
// linha na serial, lida pelo .specs/ferramentas/medir.py:
//   MEDIDA;<https|heartbeat|mqtt|mqtt-conexao>;<ms>;<bytes enviados>;<bytes recebidos>;<ok 1/0>

class ClienteContado : public WiFiClientSecure {

public:

  size_t enviados = 0;
  size_t recebidos = 0;

  void zerar() {
    enviados = 0;
    recebidos = 0;
  }

  size_t write(uint8_t dado) override {
    size_t n = WiFiClientSecure::write(dado);
    enviados += n;
    return n;
  }

  size_t write(const uint8_t *dados, size_t tamanho) override {
    size_t n = WiFiClientSecure::write(dados, tamanho);
    enviados += n;
    return n;
  }

  int read() override {
    int c = WiFiClientSecure::read();
    if (c >= 0) {
      recebidos++;
    }
    return c;
  }

  int read(uint8_t *dados, size_t tamanho) override {
    int n = WiFiClientSecure::read(dados, tamanho);
    if (n > 0) {
      recebidos += n;
    }
    return n;
  }
};


void registrarMedida(const char *tipo, unsigned long ms, size_t enviados, size_t recebidos, bool ok) {

  Serial.printf("MEDIDA;%s;%lu;%u;%u;%d\n", tipo, ms, (unsigned)enviados, (unsigned)recebidos, ok ? 1 : 0);
}

/*
 ==========================================================
 COLDTRACK EDGE
 Monitoramento IoT de Transporte Refrigerado

 ESP32-C3 + DHT + LEDs + Wi-Fi + Azure

 Envio: POST JSON via HTTPS (TLS validado) na Azure Function
 {"deviceId":"coldtrack-01","temperatura":12.4,"umidade":81.0,"rssi":-58,"medidoEm":1790000000}
 Sem leitura valida (sensor em falha): POST /api/heartbeat
 {"deviceId":"coldtrack-01","motivo":"sensor_falha","fw":"2026.11.17.2","rssi":-58,"seq":42}
 ==========================================================
*/

// ================= CONFIGURACAO DO SENSOR =================
//
// Wi-Fi, ID e chave chegam pelo cabo USB: painel > Sensores > "Conectar
// sensor pelo cabo" (Web Serial) e ficam guardados na flash.
// Sem nada salvo, vale o que estiver no secrets.h (e assim no Wokwi).
// Sem nenhum dos dois, o sensor so mede e espera o cabo.

#define FW_VERSAO "2026.11.17.3"

#ifndef AZURE_FUNCTION_URL
#define AZURE_FUNCTION_URL "https://func-coldtrack-7319.azurewebsites.net/api/telemetria"
#endif

// Heartbeat (POST /api/heartbeat): enviado no ciclo em que nao ha leitura valida
// (sensor em falha), para o painel ver a placa viva. Por padrao, a mesma URL da
// telemetria com /heartbeat no lugar de /telemetria. Nao vai para a fila
// offline: um sinal de vida atrasado nao diz nada sobre agora.
#ifndef AZURE_HEARTBEAT_URL
#define AZURE_HEARTBEAT_URL urlHeartbeatCore(AZURE_FUNCTION_URL).c_str()
#endif

// Tempo para testar uma rede nova recebida pelo cabo, em ms. Rede que o scan
// achou ganha mais tempo: em rede cheia (campus) o DHCP demora a responder.
#define TESTE_WIFI_MS 15000
#define TESTE_WIFI_ACHADA_MS 25000

// Abaixo deste sinal (dBm), handshake que estoura e sinal fraco, nao senha errada.
#define RSSI_FRACO -80

// Intervalo entre tentativas de reconexao no loop, em ms. No meio delas o
// proprio driver segue tentando; o loop continua medindo e guardando na fila.
#define RECONEXAO_MS 30000

// Maximo de redes na resposta do comando "redes".
#define REDES_MAX 15

// Scan recusado pelo driver (estacao no meio de uma conexao): quantas vezes
// tentar, e a espera antes da proxima (cresce a cada tentativa), em ms.
#define SCAN_TENTATIVAS 4
#define SCAN_ESPERA_MS 500

String cfgSsid;
String cfgSenha;
String cfgId;
String cfgChave;

// ID e chave sao lidos pela tarefa de envio e trocados pela configuracao pelo
// cabo (loop): a troca e a leitura passam por esta trava.
SemaphoreHandle_t cfgTrava = nullptr;


String copiarCfg(const String &campo) {

  if (cfgTrava) {
    xSemaphoreTake(cfgTrava, portMAX_DELAY);
  }
  String copia = campo;
  if (cfgTrava) {
    xSemaphoreGive(cfgTrava);
  }
  return copia;
}

// Melhor AP com o nome pedido, visto no scan antes do teste de rede. Fica
// aqui no topo porque o Arduino gera os prototipos antes da primeira funcao.
struct ApVisto {
  bool escaneou;
  bool achou;
  int32_t rssi;
  int32_t canal;
  wifi_auth_mode_t seguranca;
};

ApVisto ultimoAp = { false, false, 0, 0, WIFI_AUTH_OPEN };


// Limites de cada envio. Somados, o pior caso de uma requisicao HTTPS fica
// em ~17 s, bem abaixo do watchdog. O envio roda em tarefa propria: nem esse
// pior caso atrasa a proxima medicao.
#define HTTP_TIMEOUT_MS     5000   // resposta do servidor, em ms
#define CONEXAO_TIMEOUT_MS  4000   // conexao TCP, em ms
#define TLS_HANDSHAKE_S     8      // handshake TLS, em s (o padrao do core e 120 s)

// Serial USB (ESP32-C3): com o cabo num computador que nao esta lendo a porta,
// cada escrita esperava ate 2 s (20 x 100 ms) e um ciclo com ~25 prints levava
// ~58 s a mais (ciclo de 78 s medido em 17/11). Com 5 ms, o que nao cabe no
// buffer e descartado: o log se perde, a medicao nao atrasa.
#define SERIAL_TX_TIMEOUT_MS 5

// ================= STORE-AND-FORWARD =================
//
// Sem conexao (estrada sem sinal), a leitura fica guardada na flash
// e e reenviada quando a conexao volta, com o horario da medicao.

// Toda leitura entra na fila ANTES do envio (gravada logo depois de ganhar o
// numero de sequencia) e so sai quando a nuvem confirma. Um reinicio no meio
// do envio (watchdog, gravacao, porta serial aberta com DTR) nao perde a
// leitura: ela sai depois do boot com o mesmo seq e medidoEm, e a nuvem
// responde 200 se ja tinha gravado.

#define FILA_ARQUIVO      "/fila.jsonl"
#define FILA_MAX          500   // ~2h45 de leituras a cada 20 s
#define REENVIO_POR_LOTE  10    // linhas lidas da flash por vez

// Leitura sem relogio (NTP ainda nao respondeu) sai sem medidoEm se for
// recente (a nuvem usa a hora da chegada); mais velha, espera o relogio.
#define SEM_RELOGIO_RECENTE_MS 40000

// Teste: finge conexao caida por N segundos (0 = desligado), a partir de
// SIMULAR_QUEDA_INICIO_S segundos ligado (padrao 0: desde o boot).
#ifndef SIMULAR_QUEDA_S
#define SIMULAR_QUEDA_S 0
#endif
#ifndef SIMULAR_QUEDA_INICIO_S
#define SIMULAR_QUEDA_INICIO_S 0
#endif

// Teste (simulador): com SIMULAR_API_STATUS definido, o envio nao sai da
// placa e devolve esse status HTTP (201 = gravado, 401 = chave recusada...).
// Serve para provar a tela e o LED sem escrever na API de producao.
// SIMULAR_ENVIO_MS: quanto o envio simulado demora (padrao 800 ms, uma
// requisicao normal; 35000 prova que envio lento nao empurra a medicao).
#ifndef SIMULAR_ENVIO_MS
#define SIMULAR_ENVIO_MS 800
#endif

// Teste: reinicia a placa no meio do primeiro envio depois de N segundos
// ligada (0 = desligado), para provar que a leitura em curso nao se perde.
// Depois desse reinicio (por software) nao reinicia de novo.
#ifndef SIMULAR_REINICIO_ENVIO_S
#define SIMULAR_REINICIO_ENVIO_S 0
#endif

// Teste: finge relogio sem sincronizar nos primeiros N segundos (0 = desligado).
#ifndef SIMULAR_SEM_RELOGIO_S
#define SIMULAR_SEM_RELOGIO_S 0
#endif

// Teste: trava o loop uma vez depois de N segundos ligado (0 = desligado),
// para conferir o watchdog. Depois do reinicio por watchdog nao trava de novo.
#ifndef SIMULAR_TRAVAMENTO_S
#define SIMULAR_TRAVAMENTO_S 0
#endif

// Epoch minimo aceito como relogio sincronizado (nov/2023).
#define EPOCH_VALIDO 1700000000

int filaTamanho = 0;

// ================= PINAGEM =================

#define DHT_PIN 4
// DHT22 na simulacao Wokwi. Na placa fisica com DHT11, defina
// DHT_TYPE DHT11 no secrets.h (ele e incluido antes deste ponto).
#define DHT11 11
#define DHT22 22
#ifndef DHT_TYPE
#define DHT_TYPE DHT22
#endif

// Placa fisica (ESP32-C3 com OLED 0.42" embutido): TELA_OLED no secrets.h.
// Nela os GPIO 5 e 6 sao o I2C da tela, entao os LEDs saem e o status vai
// para a tela. Sem TELA_OLED (Wokwi) continuam os tres LEDs.
#ifdef TELA_OLED
#include <Wire.h>
#include <U8g2lib.h>
#define TELA_SDA 5
#define TELA_SCL 6
U8G2_SSD1306_72X40_ER_F_HW_I2C tela(U8G2_R0, U8X8_PIN_NONE, TELA_SCL, TELA_SDA);
#else
#define LED_VERDE    5
#define LED_AMARELO  6
#define LED_VERMELHO 7
#endif



// ==========================================================
// LEITURA DO DHT (leitor proprio)
// ==========================================================
//
// A biblioteca DHT desliga as interrupcoes durante a leitura; com o sensor
// mudo (mau contato) o watchdog reinicia a placa em loop. Este leitor mede
// o sinal sem desligar nada, com limite de tempo em cada pulso, e so aceita
// o dado com o checksum certo. O pino fica em dreno aberto: so puxa para
// baixo, nunca empurra 3,3 V na linha (o resistor do modulo faz o alto).

// Converte os 5 bytes do sensor. false = checksum errado.
bool decodificarDht(const uint8_t d[5], int tipo, float *temperatura, float *umidade) {

  if (((d[0] + d[1] + d[2] + d[3]) & 0xFF) != d[4]) {
    return false;
  }

  if (tipo == DHT11) {
    *umidade = d[0] + d[1] * 0.1;
    *temperatura = d[2] + (d[3] & 0x7F) * 0.1;
    if (d[3] & 0x80) {
      *temperatura = -*temperatura;
    }
  } else {
    *umidade = ((d[0] << 8) | d[1]) * 0.1;
    *temperatura = (((d[2] & 0x7F) << 8) | d[3]) * 0.1;
    if (d[2] & 0x80) {
      *temperatura = -*temperatura;
    }
  }

  return true;
}


// Espera o pino sair do nivel dado; devolve a duracao em us ou -1 no limite.
int esperarNivel(int nivel, int limiteUs) {

  uint32_t inicio = micros();

  while (gpio_get_level((gpio_num_t)DHT_PIN) == nivel) {
    if (micros() - inicio > (uint32_t)limiteUs) {
      return -1;
    }
  }

  return micros() - inicio;
}


// DHT22 (simulador Wokwi): a leitura dos 40 bits roda sem interrupcoes.
// No simulador, as tarefas do Wi-Fi interrompem o laco no meio dos pulsos:
// o pulso medido estica (bit 0 vira 1) ou passa do limite, e nenhuma
// leitura fecha o checksum. Com os limites de cada pulso, o trecho sem
// interrupcoes dura no maximo ~10 ms, bem abaixo do watchdog. O DHT11 da
// placa fisica segue lendo com as interrupcoes ligadas, como antes.
#if DHT_TYPE == DHT22
portMUX_TYPE dhtTrava = portMUX_INITIALIZER_UNLOCKED;
#define DHT_TRAVAR()  portENTER_CRITICAL(&dhtTrava)
#define DHT_LIBERAR() portEXIT_CRITICAL(&dhtTrava)
#else
#define DHT_TRAVAR()
#define DHT_LIBERAR()
#endif


// Resposta do sensor e os 40 bits. false = sensor mudo ou pulso fora do tempo.
bool lerBitsDht(uint8_t d[5]) {

  // Resposta: sobe, cai ~80 us, sobe ~80 us.
  if (esperarNivel(1, 200) < 0 || esperarNivel(0, 200) < 0 || esperarNivel(1, 200) < 0) {
    return false;
  }

  // 40 bits: ~50 us em baixo + alto de ~27 us (0) ou ~70 us (1).
  for (int i = 0; i < 40; i++) {

    if (esperarNivel(0, 120) < 0) {
      return false;
    }

    int alto = esperarNivel(1, 120);

    if (alto < 0) {
      return false;
    }

    d[i / 8] = (d[i / 8] << 1) | (alto > 45 ? 1 : 0);
  }

  return true;
}


bool lerDhtUmaVez(float *temperatura, float *umidade) {

  static bool preparado = false;

  if (!preparado) {
    gpio_reset_pin((gpio_num_t)DHT_PIN);
    gpio_set_direction((gpio_num_t)DHT_PIN, GPIO_MODE_INPUT_OUTPUT_OD);
    gpio_set_pull_mode((gpio_num_t)DHT_PIN, GPIO_PULLUP_ONLY);
    gpio_set_level((gpio_num_t)DHT_PIN, 1);
    preparado = true;
    esperarAtualizando(1000);  // o sensor precisa de ~1 s depois de ligado
  }

  // Pedido de leitura: linha em baixo (DHT11 pede 18 ms; DHT22, ~1 ms).
  gpio_set_level((gpio_num_t)DHT_PIN, 0);
  if (DHT_TYPE == DHT11) {
    delay(20);
  } else {
    delayMicroseconds(1100);
  }
  uint8_t d[5] = {0, 0, 0, 0, 0};

  DHT_TRAVAR();
  gpio_set_level((gpio_num_t)DHT_PIN, 1);
  bool recebido = lerBitsDht(d);
  DHT_LIBERAR();

  if (!recebido) {
    return false;
  }

  return decodificarDht(d, DHT_TYPE, temperatura, umidade);
}


// Duas tentativas (um pulso esticado por interrupcao do Wi-Fi erra o checksum).
// Sem leitura valida, devolve false e NAN nos dois valores.
bool lerSensor(float *temperatura, float *umidade) {

  for (int tentativa = 0; tentativa < 2; tentativa++) {

    if (tentativa > 0) {
      esperarAtualizando(DHT_TYPE == DHT11 ? 1100 : 2100);
    }

    if (lerDhtUmaVez(temperatura, umidade)) {
      return true;
    }
  }

  *temperatura = NAN;
  *umidade = NAN;
  return false;
}


#ifdef TESTE_DHT
// Autoteste da conversao (compilar com -DTESTE_DHT): casos com resposta conhecida.
void autotesteDht() {

  struct Caso { const char *nome; uint8_t d[5]; int tipo; bool valido; float t; float u; };

  const Caso casos[] = {
    { "DHT11 31.8C 61%",      { 61, 0, 31, 8, 100 },          DHT11, true,  31.8,  61.0 },
    { "DHT11 checksum errado", { 61, 0, 31, 8, 101 },          DHT11, false, 0, 0 },
    { "DHT22 24.6C 55.3%",    { 0x02, 0x29, 0x00, 0xF6, 0x21 }, DHT22, true,  24.6,  55.3 },
    { "DHT22 -10.1C 40.0%",   { 0x01, 0x90, 0x80, 0x65, 0x76 }, DHT22, true,  -10.1, 40.0 },
    { "DHT22 checksum errado", { 0x02, 0x29, 0x00, 0xF6, 0x20 }, DHT22, false, 0, 0 },
  };

  int falhas = 0;

  for (const Caso &c : casos) {

    float t = 0, u = 0;
    bool ok = decodificarDht(c.d, c.tipo, &t, &u);
    bool bate = (ok == c.valido) && (!ok || (fabs(t - c.t) < 0.05 && fabs(u - c.u) < 0.05));

    Serial.printf("TESTE_DHT %-24s %s (valido=%d t=%.1f u=%.1f)\n",
                  c.nome, bate ? "OK" : "FALHOU", ok, t, u);

    if (!bate) {
      falhas++;
    }
  }

  Serial.printf("TESTE_DHT: %d falha(s)\n", falhas);
}
#endif


// ================= FAIXA DA CARGA =================
//
// Faixa normal [min, max]; ate `margem` graus fora dela e ATENCAO, alem disso
// CRITICO. Comeca no perfil demonstrativo (normal ate 15, atencao ate 20) e
// passa a ser a do perfil de carga do veiculo, que volta em cada resposta da
// nuvem. Fica guardada na flash: sem sinal, o LED segue a ultima faixa recebida.

Preferences preferencias;

float faixaMin = NAN;      // NAN = sem limite inferior
float faixaMax = 15.0;
float faixaMargem = 5.0;


// ================= NUMERO DE SEQUENCIA =================
//
// Cada leitura valida ganha um numero: 1, 2, 3... Vai no payload e na fila
// offline, e fica na flash (Preferences): depois de um reinicio a contagem
// continua de onde parou. Buraco na sequencia, no banco, e leitura perdida
// entre o sensor e a nuvem. Gravar a cada 20 s da ~4.300 escritas/dia; o NVS
// espalha as escritas pelas paginas da particao (desgaste da ordem de anos).

uint32_t seqAtual = 0;   // ultimo numero usado


void carregarSeq() {

  preferencias.begin("coldtrack", true);
  seqAtual = preferencias.getULong("seq", 0);
  preferencias.end();
}


uint32_t proximaSeq() {

  seqAtual++;

  if (seqAtual == 0) {   // deu a volta no uint32 (~2.700 anos a cada 20 s)
    seqAtual = 1;
  }

  preferencias.begin("coldtrack", false);
  preferencias.putULong("seq", seqAtual);
  preferencias.end();

  return seqAtual;
}


// ================= WATCHDOG =================
//
// Watchdog de tarefa (TWDT) no loop: se o loop passar WATCHDOG_S sem
// alimentar o watchdog (travou em rede, flash ou sensor), a placa reinicia.
// A fila (LittleFS) e a sequencia (Preferences) estao na flash, entao o
// envio retoma sozinho depois do reinicio. Vigia as duas tarefas: o loop
// (medicao) e a tarefa de envio. Os trechos longos alimentam o watchdog no
// meio; o pior caso legitimo entre duas alimentacoes e uma requisicao HTTPS
// ou uma conexao MQTT (4 s de TCP + 8 s de TLS + 5 s de resposta).

#ifndef WATCHDOG_S
#define WATCHDOG_S 60
#endif


void iniciarWatchdog() {

  esp_task_wdt_config_t config = {
    .timeout_ms = WATCHDOG_S * 1000,
    .idle_core_mask = (1 << portNUM_PROCESSORS) - 1,   // tarefa ociosa tambem
    .trigger_panic = true,   // estourou: reinicia a placa
  };

  // O core do Arduino ja inicia o watchdog (5 s, so a tarefa ociosa):
  // reconfigura; se nao estiver iniciado, inicia.
  if (esp_task_wdt_reconfigure(&config) == ESP_ERR_INVALID_STATE) {
    esp_task_wdt_init(&config);
  }

  if (esp_task_wdt_status(NULL) == ESP_ERR_NOT_FOUND) {
    esp_task_wdt_add(NULL);   // tarefa do loop
  }
}


void alimentarWatchdog() {

  esp_task_wdt_reset();
}


bool reiniciouPorWatchdog() {

  esp_reset_reason_t motivo = esp_reset_reason();

  return motivo == ESP_RST_TASK_WDT || motivo == ESP_RST_INT_WDT || motivo == ESP_RST_WDT;
}


// ================= TEMPORIZAÇÃO =================

// Uma leitura a cada 20 segundos: detecta desvio rapido sem
// gastar dado a toa quando a conexao for celular.
//
// Heartbeat: a propria leitura e o sinal de vida. A nuvem marca o sensor
// online pelo horario da ultima leitura recebida; nao ha mensagem separada.
// Sensor mudo (DHT sem resposta) para de enviar e aparece offline no painel:
// sem medicao nao ha garantia da carga, e esse e o alerta certo.

// Agenda fixa: 20 s do inicio de um ciclo ao inicio do seguinte. O envio
// (HTTPS, MQTT, fila) roda na tarefa de envio e nao empurra a medicao.
const unsigned long INTERVALO_ENVIO = 20000;

unsigned long proximoCiclo = 0;     // millis() marcado para o proximo ciclo
bool cicloImediato = true;          // mede ja (boot, configuracao pelo cabo)


// ================= TAREFA DE ENVIO =================
//
// O loop mede, numera, grava na fila e avisa; esta tarefa esvazia a fila
// (HTTPS), manda o heartbeat e publica no MQTT. Rede lenta ou fora do ar
// atrasa so o envio, nunca o proximo ciclo.

TaskHandle_t tarefaEnvioHandle = nullptr;
SemaphoreHandle_t filaTrava = nullptr;   // fila na flash: o loop grava, a tarefa de envio le e apaga

volatile bool pausaEnvio = false;        // configuracao pelo cabo mexendo na rede/identidade
volatile bool envioOcupado = false;      // tarefa de envio no meio de uma requisicao
volatile bool heartbeatPendente = false;
volatile unsigned long heartbeatPedidoEm = 0;

// Ultima leitura para o MQTT (so a do ciclo, feita com rede).
portMUX_TYPE mqttLeituraTrava = portMUX_INITIALIZER_UNLOCKED;
struct LeituraMqtt {
  bool pendente;
  float temperatura;
  float umidade;
  long rssi;
  unsigned long em;
};
LeituraMqtt leituraMqtt = { false, 0, 0, 0, 0 };


// Trava da fila enquanto o objeto existe (recursiva: uma funcao com a trava
// pode chamar outra que tambem trava).
class TravaFila {
public:
  TravaFila() {
    if (filaTrava) {
      xSemaphoreTakeRecursive(filaTrava, portMAX_DELAY);
    }
  }
  ~TravaFila() {
    if (filaTrava) {
      xSemaphoreGiveRecursive(filaTrava);
    }
  }
};


void avisarEnvio() {

  if (tarefaEnvioHandle) {
    xTaskNotifyGive(tarefaEnvioHandle);
  }
}


// ==========================================================
// INDICADORES (tela OLED e LEDs)
// ==========================================================
//
// Mostram o que a placa esta fazendo, sem computador por perto.
//
// Tela 72x40 (placa fisica, TELA_OLED):
//   linha 1, fonte grande: temperatura (--.- sem leitura valida)
//   linha 2: status da carga e umidade ("NORMAL   81%"), ou FALHA SENSOR,
//            CONFIG CABO, SEM CONFIG, INICIANDO, REINICIO WDT
//   linha 3: fase da conexao: CONECTANDO, WIFI -58dBm, SEM REDE, FILA 12,
//            ENVIANDO..., ENVIADO, ERRO API 401, FALHA ENVIO, TESTANDO...
// Linha com duas informacoes (SEM REDE e FILA n; CONECTANDO e o nome da
// rede) alterna a cada 2 s.
//
// LEDs: os tres LEDs de faixa (simulacao) e, se o secrets.h definir, o LED da
// placa (LED_PLACA). Padroes em docs/como-funciona.md (3.12).
//
// Nada aqui espera: o estado vem de variaveis e o piscar vem do millis().
// Quem precisa esperar (Wi-Fi, scan, sensor) chama esperarAtualizando(), que
// segue animando durante a espera.

// LED da placa fisica (opcional, no secrets.h):
//   #define LED_PLACA 8                 // GPIO do LED
//   #define LED_PLACA_ATIVO_BAIXO       // LED acende com o pino em 0
//   #define LED_PLACA_RGB               // LED RGB enderecavel (WS2812)

#define FAIXA_NENHUMA -1
#define FAIXA_NORMAL   0
#define FAIXA_ATENCAO  1
#define FAIXA_CRITICO  2

#define CABO_NADA      0
#define CABO_TESTANDO  1
#define CABO_RESULTADO 2

#define CABO_RESULTADO_MS 8000   // tempo do resultado do teste na tela
#define ENVIADO_MS        4000   // tempo do "ENVIADO" na tela
#define PAGINA_MS         2000   // troca da informacao alternada
#define AVISO_WDT_MS      60000  // aviso de reinicio por watchdog depois do boot

int indFaixa = FAIXA_NENHUMA;     // ultima leitura valida
float indTemperatura = NAN;
float indUmidade = NAN;
bool indSensorFalhou = false;
bool indIniciando = true;         // ate o fim do setup
bool indConectando = false;       // esperando o Wi-Fi em conectarWiFi()
bool indEnviando = false;
int indUltimoHttp = 0;            // 0 = nada enviado ainda; <0 falha de rede
unsigned long indEnviadoEm = 0;
bool indReinicioWdt = false;
int indCabo = CABO_NADA;
String indCaboSsid;
String indCaboResultado;
unsigned long indCaboEm = 0;
unsigned long indUltimaAtualizacao = 0;


bool semConfiguracao() {

  return cfgSsid.length() == 0 || !temIdentidade();
}


bool erroNoEnvio() {

  return indUltimoHttp != 0 && indUltimoHttp != 200 && indUltimoHttp != 201;
}


// Resultado do teste de rede pelo cabo, em ate 12 letras.
const char *resumoCabo(const String &erro) {

  if (erro.length() == 0)               return "REDE OK";
  if (erro == "senha")                  return "SENHA ERRADA";
  if (erro == "rede_nao_encontrada")    return "REDE AUSENTE";
  if (erro == "rede_corporativa")       return "REDE CORPOR.";
  if (erro == "seguranca_incompativel") return "SEG. INCOMP.";
  if (erro == "sinal_fraco")            return "SINAL FRACO";
  if (erro == "sem_ip")                 return "SEM IP";
  if (erro == "tempo")                  return "TEMPO ESGOT.";
  if (erro == "sem_identidade")         return "SEM ID";
  if (erro == "identidade_invalida")    return "ID INVALIDO";
  if (erro == "rede_invalida")          return "REDE INVALID";
  return "ERRO";
}


// Liga cada cor. Simulacao: um LED por cor. LED da placa: RGB mostra a cor;
// LED de uma cor so acende (perde a cor, mantem o padrao de piscar).
void escreverLeds(bool verde, bool amarelo, bool vermelho) {

  static int anterior = -1;
  int estado = (verde ? 1 : 0) | (amarelo ? 2 : 0) | (vermelho ? 4 : 0);

  if (estado == anterior) {
    return;
  }

  anterior = estado;

#ifndef TELA_OLED
  digitalWrite(LED_VERDE, verde ? HIGH : LOW);
  digitalWrite(LED_AMARELO, amarelo ? HIGH : LOW);
  digitalWrite(LED_VERMELHO, vermelho ? HIGH : LOW);
#endif

#ifdef LED_PLACA
#ifdef LED_PLACA_RGB
  if (estado == 7) {
    rgbLedWrite(LED_PLACA, 40, 40, 40);    // todas: branco
  } else if (amarelo) {
    rgbLedWrite(LED_PLACA, 60, 35, 0);
  } else if (vermelho) {
    rgbLedWrite(LED_PLACA, 60, 0, 0);
  } else if (verde) {
    rgbLedWrite(LED_PLACA, 0, 50, 0);
  } else {
    rgbLedWrite(LED_PLACA, 0, 0, 0);
  }
#else
  bool aceso = estado != 0;
#ifdef LED_PLACA_ATIVO_BAIXO
  aceso = !aceso;
#endif
  digitalWrite(LED_PLACA, aceso ? HIGH : LOW);
#endif
#endif
}


// Padrao de piscar pela fase. Devolve o nome (vai para a serial quando muda).
const char *atualizarLeds(unsigned long t) {

  bool aceso = true;
  const char *nome;

  if (indCabo == CABO_TESTANDO ||
      (indFaixa == FAIXA_NENHUMA && !indSensorFalhou && (indIniciando || !semConfiguracao()))) {

    // Iniciando, conectando sem leitura ainda, ou testando rede pelo cabo:
    // verde, amarelo, vermelho em sequencia (200 ms cada).
    int passo = (t / 200) % 3;
    escreverLeds(passo == 0, passo == 1, passo == 2);
    return "sequencia";
  }

  if (semConfiguracao()) {

    // Sem rede ou sem identidade salvas: amarelo, dois toques a cada 1,5 s.
    unsigned long f = t % 1500;
    escreverLeds(false, f < 150 || (f >= 300 && f < 450), false);
    return "sem_config";
  }

  if (indSensorFalhou) {

    // Sem leitura valida: os tres juntos, 2 vezes por segundo.
    aceso = (t / 250) % 2 == 0;
    escreverLeds(aceso, aceso, aceso);
    return "falha_sensor";
  }

  if (!conexaoDisponivel()) {
    aceso = (t / 500) % 2 == 0;       // 1 piscada por segundo
    nome = "sem_rede";
  } else if (erroNoEnvio()) {
    aceso = (t / 125) % 2 == 0;       // 4 piscadas por segundo
    nome = "erro_envio";
  } else {
    nome = "fixo";
  }

  escreverLeds(aceso && indFaixa == FAIXA_NORMAL,
               aceso && indFaixa == FAIXA_ATENCAO,
               aceso && indFaixa == FAIXA_CRITICO);
  return nome;
}


// Textos das linhas 2 e 3 (no maximo 12 letras cada, fonte 6x10).
void montarStatus(unsigned long t, char *l2, char *l3, size_t n) {

  bool pagina = (t / PAGINA_MS) % 2 == 1;

  // ---- linha 2: carga ou situacao da placa ----
  if (indCabo != CABO_NADA) {
    snprintf(l2, n, "CONFIG CABO");
  } else if (indSensorFalhou) {
    snprintf(l2, n, "FALHA SENSOR");
  } else if (indFaixa != FAIXA_NENHUMA) {
    const char *faixa = indFaixa == FAIXA_NORMAL ? "NORMAL" :
                        indFaixa == FAIXA_ATENCAO ? "ATENCAO" : "CRITICO";
    snprintf(l2, n, "%-7s %3.0f%%", faixa, indUmidade);
  } else if (indReinicioWdt) {
    snprintf(l2, n, "REINICIO WDT");
  } else if (!indIniciando && semConfiguracao()) {
    snprintf(l2, n, "SEM CONFIG");
  } else {
    snprintf(l2, n, "INICIANDO");
  }

  // ---- linha 3: conexao ----
  if (indCabo == CABO_TESTANDO) {
    snprintf(l3, n, "%.12s", pagina ? indCaboSsid.c_str() : "TESTANDO...");
  } else if (indCabo == CABO_RESULTADO) {
    snprintf(l3, n, "%s", indCaboResultado.c_str());
  } else if (indConectando) {
    snprintf(l3, n, "%.12s", pagina ? cfgSsid.c_str() : "CONECTANDO");
  } else if (indIniciando) {
    l3[0] = '\0';
  } else if (semConfiguracao()) {
    snprintf(l3, n, "LIGUE O CABO");
  } else if (indReinicioWdt && pagina && t < AVISO_WDT_MS && indFaixa != FAIXA_NENHUMA) {
    snprintf(l3, n, "REINICIO WDT");
  } else if (indEnviando) {
    snprintf(l3, n, "ENVIANDO...");
  } else if (!conexaoDisponivel()) {
    if (pagina && filaTamanho > 0) {
      snprintf(l3, n, "FILA %d", filaTamanho);
    } else {
      snprintf(l3, n, "SEM REDE");
    }
  } else if (indUltimoHttp < 0) {
    snprintf(l3, n, "FALHA ENVIO");
  } else if (erroNoEnvio()) {
    snprintf(l3, n, "ERRO API %d", indUltimoHttp);
  } else if (indEnviadoEm != 0 && t - indEnviadoEm < ENVIADO_MS) {
    snprintf(l3, n, "ENVIADO");
  } else {
    long rssi = WiFi.RSSI();
    if (rssi < 0) {
      snprintf(l3, n, "WIFI %lddBm", rssi);
    } else {
      snprintf(l3, n, "WIFI OK");   // simulador: sem RSSI
    }
  }
}


#ifdef TELA_OLED

// Redesenha so quando o texto muda (o I2C leva alguns ms por quadro).
void desenharTela(const char *l2, const char *l3) {

  static char anterior[3][16] = { "?", "?", "?" };
  char l1[16];

  if (isnan(indTemperatura)) {
    snprintf(l1, sizeof(l1), "--.-\xb0" "C");
  } else {
    snprintf(l1, sizeof(l1), "%.1f\xb0" "C", indTemperatura);
  }

  if (!strcmp(l1, anterior[0]) && !strcmp(l2, anterior[1]) && !strcmp(l3, anterior[2])) {
    return;
  }

  strncpy(anterior[0], l1, 15);
  strncpy(anterior[1], l2, 15);
  strncpy(anterior[2], l3, 15);

  tela.clearBuffer();

  tela.setFont(u8g2_font_helvB14_tf);
  tela.drawStr(0, 15, l1);

  tela.setFont(u8g2_font_6x10_tf);
  tela.drawStr(0, 28, l2);
  tela.drawStr(0, 39, l3);

  tela.sendBuffer();
}

#endif


void desenharIndicadores() {

  unsigned long t = millis();

  if (indCabo == CABO_RESULTADO && t - indCaboEm >= CABO_RESULTADO_MS) {
    indCabo = CABO_NADA;
  }

  static const char *ledAnterior = "";
  const char *led = atualizarLeds(t);

  if (strcmp(led, ledAnterior) != 0) {
    ledAnterior = led;
    Serial.print("LED: ");
    Serial.println(led);
  }

#ifdef TELA_OLED
  char l2[16];
  char l3[16];
  montarStatus(t, l2, l3, sizeof(l2));
  desenharTela(l2, l3);
#endif

  indUltimaAtualizacao = t;
}


// Chamada a cada volta do loop: no maximo a cada 50 ms.
void atualizarIndicadores() {

  if (millis() - indUltimaAtualizacao >= 50) {
    desenharIndicadores();
  }
}


// delay() que continua animando a tela e o LED.
void esperarAtualizando(unsigned long ms) {

  unsigned long inicio = millis();

  while (millis() - inicio < ms) {
    atualizarIndicadores();
    unsigned long falta = ms - (millis() - inicio);
    delay(falta < 20 ? falta : 20);
  }
}


void statusNormal() {

  indFaixa = FAIXA_NORMAL;
  Serial.println("STATUS DA CARGA: NORMAL");
}


void statusAtencao() {

  indFaixa = FAIXA_ATENCAO;
  Serial.println("STATUS DA CARGA: ATENCAO");
}


void statusCritico() {

  indFaixa = FAIXA_CRITICO;
  Serial.println("STATUS DA CARGA: CRITICO");
}


// ==========================================================
// CONFIGURACAO (flash ou secrets.h)
// ==========================================================

void carregarConfig() {

  preferencias.begin("config", true);
  cfgSsid = preferencias.getString("ssid", "");
  cfgSenha = preferencias.getString("senha", "");
  cfgId = preferencias.getString("id", "");
  cfgChave = preferencias.getString("chave", "");
  preferencias.end();

  if (cfgSsid.length() == 0) {
#ifdef WIFI_SSID
    cfgSsid = WIFI_SSID;
#endif
#ifdef WIFI_PASSWORD
    cfgSenha = WIFI_PASSWORD;
#endif
  }

  if (cfgId.length() == 0 || cfgChave.length() == 0) {
#if defined(DEVICE_ID) && defined(DEVICE_KEY)
    cfgId = DEVICE_ID;
    cfgChave = DEVICE_KEY;
#endif
  }
}


bool temIdentidade() {

  return cfgId.length() > 0 && cfgChave.length() > 0;
}


// ID sugerido para placa nova: coldtrack- + final do MAC (unico por chip).
String idDoChip() {

  String mac = WiFi.macAddress();
  mac.replace(":", "");
  mac.toLowerCase();

  return "coldtrack-" + mac.substring(6);
}


// ==========================================================
// CONEXÃO WI-FI
// ==========================================================

bool lerSerial();

// ESP32-C3 com OLED 0.42": a antena de chip nao aguenta a potencia padrao e o
// handshake com o roteador falha (sai como senha errada). Potencia menor resolve.
// O setTxPower so vale com o modo estacao ja ligado (WiFi.mode no setup).
void ajustarRadio() {
#ifdef TELA_OLED
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
#endif
}


// Motivo da ultima queda do Wi-Fi (vem do evento do driver; 0 = nenhum) e se
// a placa chegou a se associar ao AP (WPA concluido) na tentativa atual.
volatile uint8_t motivoQueda = 0;
volatile bool associou = false;
unsigned long ultimaTentativaWiFi = 0;


void logMotivo(const char *contexto) {

  if (motivoQueda == 0) {
    return;
  }

  Serial.printf("WIFI: %s, motivo %u (%s)\n", contexto, motivoQueda,
                WiFi.disconnectReasonName((wifi_err_reason_t)motivoQueda));
}


// Comeca uma tentativa do zero. Sem o disconnect antes, um begin no meio de
// outra tentativa e recusado pelo driver ("sta is connecting, cannot set
// config") e a tentativa em curso e atropelada a cada ciclo do loop.
// Scan em todos os canais e escolha pelo sinal: o padrao (fast scan) entra no
// primeiro AP com o nome, e no campus ha varios APs com o mesmo SSID.
void iniciarWiFi(const char *ssid, const char *senha) {

  WiFi.disconnect();
  delay(100);

  motivoQueda = 0;
  associou = false;
  ultimaTentativaWiFi = millis();

  WiFi.setScanMethod(WIFI_ALL_CHANNEL_SCAN);
  WiFi.setSortMethod(WIFI_CONNECT_AP_BY_SIGNAL);

  // Potencia antes do begin (vale ja para a associacao) e de novo depois, caso
  // o driver reaplique a potencia padrao ao conectar.
  ajustarRadio();
  WiFi.begin(ssid, senha);
  ajustarRadio();

#ifdef TELA_OLED
  Serial.printf("RADIO: potencia maxima %.1f dBm\n", WiFi.getTxPower() / 4.0);
#endif
}


void conectarWiFi() {

  if (cfgSsid.length() == 0) {

    Serial.println("Wi-Fi nao configurado. Ligue o sensor no cabo e configure pelo painel.");
    return;
  }

  Serial.println();
  Serial.print("Conectando ao Wi-Fi ");
  Serial.print(cfgSsid);

  iniciarWiFi(cfgSsid.c_str(), cfgSenha.c_str());

  int tentativas = 0;
  indConectando = true;

  while (WiFi.status() != WL_CONNECTED && tentativas < 20) {

    esperarAtualizando(500);
    alimentarWatchdog();

    Serial.print(".");

    tentativas++;

    // Chegou configuracao pelo cabo: para de esperar e deixa o loop tratar.
    if (lerSerial()) {
      break;
    }
  }

  indConectando = false;

  if (WiFi.status() == WL_CONNECTED) {

    Serial.println();
    Serial.println("Wi-Fi conectado!");

    Serial.print("IP: ");
    Serial.println(WiFi.localIP());

    Serial.print("RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");

  } else {

    Serial.println();
    Serial.println("Falha na conexão Wi-Fi. O driver segue tentando em segundo plano.");
    logMotivo("sem conexao");
  }
}


// ==========================================================
// ENVIO PARA AZURE (JSON via HTTPS)
// ==========================================================

// ==========================================================
// FAIXA DA CARGA (vem da nuvem, fica na flash)
// ==========================================================

void carregarFaixa() {

  preferencias.begin("coldtrack", true);
  faixaMin = preferencias.getFloat("min", NAN);
  faixaMax = preferencias.getFloat("max", 15.0);
  faixaMargem = preferencias.getFloat("margem", 5.0);
  preferencias.end();
}


// Resposta da nuvem: {"id":...,"status":...,"perfil":"manga","faixa":{"min":10.0,"max":13.0,"margem":3.0}}
void atualizarFaixa(const String &resposta) {

  int pos = resposta.indexOf("\"faixa\":");

  if (pos < 0) {
    return;
  }

  std::string trecho(resposta.c_str() + pos);

  float novoMin = extrairNumeroJson(trecho, "min");
  float novoMax = extrairNumeroJson(trecho, "max");
  float novaMargem = extrairNumeroJson(trecho, "margem");

  if (isnan(novoMax) || isnan(novaMargem)) {
    return;
  }

  bool mudou = novoMax != faixaMax || novaMargem != faixaMargem ||
               isnan(novoMin) != isnan(faixaMin) ||
               (!isnan(novoMin) && novoMin != faixaMin);

  if (!mudou) {
    return;
  }

  faixaMin = novoMin;
  faixaMax = novoMax;
  faixaMargem = novaMargem;

  // Grava so quando muda: poupa a flash. Objeto proprio: roda na tarefa de
  // envio, ao mesmo tempo que o loop grava o seq no `preferencias`.
  Preferences flash;
  flash.begin("coldtrack", false);
  flash.putFloat("min", faixaMin);
  flash.putFloat("max", faixaMax);
  flash.putFloat("margem", faixaMargem);
  flash.end();

  Serial.print("FAIXA: nova faixa da carga ");
  Serial.print(isnan(faixaMin) ? String("-") : String(faixaMin, 1));
  Serial.print(" a ");
  Serial.print(faixaMax, 1);
  Serial.print(" C (margem ");
  Serial.print(faixaMargem, 1);
  Serial.println(" C)");
}


// Retorna o status HTTP (201 = gravado) ou um codigo negativo de falha de rede.
int postarAzure(const char *payload) {

  if (SIMULAR_REINICIO_ENVIO_S > 0 && millis() > SIMULAR_REINICIO_ENVIO_S * 1000UL &&
      esp_reset_reason() != ESP_RST_SW) {
    Serial.println("TESTE: reiniciando a placa no meio do envio.");
    Serial.flush();
    ESP.restart();
  }

#ifdef SIMULAR_API_STATUS
  delay(SIMULAR_ENVIO_MS);   // tempo da requisicao (tarefa de envio: nao desenha a tela)
  Serial.print("Azure (SIMULADO, nada saiu da placa): status ");
  Serial.println(SIMULAR_API_STATUS);
  return SIMULAR_API_STATUS;
#endif

  ClienteContado clienteSeguro;
  clienteSeguro.setCACert(AZURE_ROOT_CA);
  clienteSeguro.setHandshakeTimeout(TLS_HANDSHAKE_S);

  HTTPClient http;
  http.setConnectTimeout(CONEXAO_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);

  // Tempo e bytes do envio inteiro: conexao TCP + TLS + requisicao + resposta.
  unsigned long inicio = millis();

  if (!http.begin(clienteSeguro, AZURE_FUNCTION_URL)) {

    Serial.println("Azure: falha ao iniciar conexao HTTPS.");
    registrarMedida("https", millis() - inicio, 0, 0, false);
    return -1;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("x-device-key", copiarCfg(cfgChave));

  int status = http.POST(payload);

  if (status == 201) {

    String resposta = http.getString();

    Serial.print("Azure: gravado. Resposta: ");
    Serial.println(resposta);

    atualizarFaixa(resposta);

  }

  else if (status == 200) {

    // Reenvio de leitura que ja tinha chegado (a resposta anterior se perdeu).
    Serial.print("Azure: leitura ja estava gravada. Resposta: ");
    Serial.println(http.getString());
  }

  else {

    Serial.print("Azure: erro HTTP ");
    Serial.print(status);
    Serial.print(" ");
    Serial.println(status > 0 ? http.getString() : http.errorToString(status));
  }

  http.end();

  registrarMedida("https", millis() - inicio, clienteSeguro.enviados, clienteSeguro.recebidos,
                  status == 201 || status == 200);

  return status;
}


// Heartbeat: placa viva sem leitura valida. Retorna o status HTTP (200 = aceito)
// ou um codigo negativo de falha de rede. Falha nao vai para a fila.
int enviarHeartbeat(const char *motivo) {

  char payload[160];
  String id = copiarCfg(cfgId);
  montarHeartbeatCore(payload, sizeof(payload), id.c_str(), motivo, FW_VERSAO,
                      WiFi.RSSI(), seqAtual);

  Serial.print("HEARTBEAT: ");
  Serial.println(payload);

#ifdef SIMULAR_API_STATUS
  delay(800);
  // A rota de heartbeat responde 200 (nao cria nada); 201 simulado vira 200.
  int simulado = SIMULAR_API_STATUS == 201 ? 200 : SIMULAR_API_STATUS;
  Serial.print("HEARTBEAT (SIMULADO, nada saiu da placa): status ");
  Serial.println(simulado);
  return simulado;
#endif

  String url = AZURE_HEARTBEAT_URL;
  if (url.length() == 0) {
    Serial.println("HEARTBEAT: URL da telemetria sem /telemetria; heartbeat desligado.");
    return -1;
  }

  ClienteContado clienteSeguro;
  clienteSeguro.setCACert(AZURE_ROOT_CA);
  clienteSeguro.setHandshakeTimeout(TLS_HANDSHAKE_S);

  HTTPClient http;
  http.setConnectTimeout(CONEXAO_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);

  unsigned long inicio = millis();

  if (!http.begin(clienteSeguro, url)) {

    Serial.println("HEARTBEAT: falha ao iniciar conexao HTTPS.");
    registrarMedida("heartbeat", millis() - inicio, 0, 0, false);
    return -1;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("x-device-key", copiarCfg(cfgChave));

  int status = http.POST(payload);

  Serial.print("HEARTBEAT: status ");
  Serial.print(status);
  Serial.print(" ");
  Serial.println(status > 0 ? http.getString() : http.errorToString(status));

  http.end();

  registrarMedida("heartbeat", millis() - inicio, clienteSeguro.enviados, clienteSeguro.recebidos,
                  status == 200);

  return status;
}


// ==========================================================
// MQTT (ThingSpeak)
// ==========================================================
//
// Conexao persistente em mqtt3.thingspeak.com:8883 (TLS; a raiz e a mesma
// DigiCert Global Root G2 do Azure). Publica temperatura/umidade/RSSI no
// canal a cada ciclo, com QoS 0 (o ThingSpeak nao aceita 1 ou 2): o broker
// nao confirma a entrega. Leitura feita sem rede nao vai para o MQTT; a
// fila offline e so do HTTPS (o plano gratis aceita 1 mensagem a cada 15 s).

#ifdef COM_MQTT

#define MQTT_HOST       "mqtt3.thingspeak.com"
#define MQTT_PORTA      8883
#define MQTT_KEEPALIVE  120   // s
#define MQTT_TIMEOUT    5     // s (resposta do broker)

ClienteContado clienteMqtt;
PubSubClient mqtt(clienteMqtt);

unsigned long mqttProximaTentativa = 0;
unsigned long mqttEspera = 5000;       // backoff: 5 s, dobra ate 60 s
bool mqttAvisouRelogio = false;


// Texto do estado do PubSubClient, para a serial dizer por que caiu.
const char *estadoMqtt(int estado) {

  switch (estado) {
    case -4: return "sem resposta do broker (keep-alive)";
    case -3: return "conexao perdida";
    case -2: return "falha de rede/TLS";
    case -1: return "desconectado";
    case 0:  return "conectado";
    case 1:  return "protocolo recusado";
    case 2:  return "client id recusado";
    case 3:  return "broker indisponivel";
    case 4:  return "usuario/senha errados";
    case 5:  return "sem autorizacao (canal nao liberado para o dispositivo?)";
    default: return "desconhecido";
  }
}


bool garantirMqtt() {

  if (mqtt.connected()) {
    return true;
  }

  if (!conexaoDisponivel()) {
    return false;
  }

  // Sem relogio o certificado nao se valida: nem tenta.
  if (!relogioOk()) {
    if (!mqttAvisouRelogio) {
      Serial.println("MQTT: aguardando relogio para validar o certificado.");
      mqttAvisouRelogio = true;
    }
    return false;
  }

  if (millis() < mqttProximaTentativa) {
    return false;
  }

  clienteMqtt.setCACert(AZURE_ROOT_CA);
  clienteMqtt.setConnectionTimeout(CONEXAO_TIMEOUT_MS);
  clienteMqtt.setHandshakeTimeout(TLS_HANDSHAKE_S);
  clienteMqtt.zerar();

  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setKeepAlive(MQTT_KEEPALIVE);
  mqtt.setSocketTimeout(MQTT_TIMEOUT);

  Serial.println("MQTT: conectando ao ThingSpeak...");

  unsigned long inicio = millis();
  bool ok = mqtt.connect(MQTT_CLIENT_ID, MQTT_USUARIO, MQTT_SENHA);

  registrarMedida("mqtt-conexao", millis() - inicio, clienteMqtt.enviados, clienteMqtt.recebidos, ok);

  if (ok) {

    Serial.println("MQTT: conectado.");
    mqttEspera = 5000;
    return true;
  }

  char erroTls[80] = "";
  clienteMqtt.lastError(erroTls, sizeof(erroTls));

  Serial.printf("MQTT: falhou (%d: %s; TLS: %s). Nova tentativa em %lu s.\n",
                mqtt.state(), estadoMqtt(mqtt.state()), erroTls[0] ? erroTls : "ok", mqttEspera / 1000);

  mqttProximaTentativa = millis() + mqttEspera;
  mqttEspera = min(mqttEspera * 2, 60000UL);

  return false;
}


void publicarMqtt(float temperatura, float umidade, long rssi) {

  if (!garantirMqtt()) {
    registrarMedida("mqtt", 0, 0, 0, false);
    return;
  }

  char topico[48];
  char mensagem[64];

  snprintf(topico, sizeof(topico), "channels/%s/publish", MQTT_CANAL);

  // RSSI >= 0 (simulador) nao vai, como no HTTPS.
  if (rssi < 0) {
    snprintf(mensagem, sizeof(mensagem), "field1=%.1f&field2=%.1f&field3=%ld", temperatura, umidade, rssi);
  } else {
    snprintf(mensagem, sizeof(mensagem), "field1=%.1f&field2=%.1f", temperatura, umidade);
  }

  clienteMqtt.zerar();

  unsigned long inicio = millis();
  bool ok = mqtt.publish(topico, mensagem);

  registrarMedida("mqtt", millis() - inicio, clienteMqtt.enviados, clienteMqtt.recebidos, ok);

  Serial.print(ok ? "MQTT: publicado " : "MQTT: falha ao publicar ");
  Serial.println(mensagem);
}

#endif


// Falha que vale tentar de novo depois: rede ou servidor fora do ar.
// 4xx (dado rejeitado pelo contrato) nao melhora reenviando.
bool falhaTemporaria(int status) {

  return status <= 0 || status >= 500;
}


// ==========================================================
// RELOGIO (NTP)
// ==========================================================

// Relogio so vale depois do NTP responder neste boot. Num reinicio que nao
// e por falta de energia (watchdog, gravacao, porta aberta com DTR), o ESP32
// devolve a hora a partir do oscilador RC interno, que deriva: em 17/11 a
// leitura 266 saiu ~1 min adiantada e chegou "depois" da 270. Ate o NTP, a
// leitura e guardada com o millis() e ganha o horario quando ele responde.
volatile bool relogioSincronizado = false;


void aoSincronizarRelogio(struct timeval *tv) {

  relogioSincronizado = true;
}


void sincronizarRelogio() {

  sntp_set_time_sync_notification_cb(aoSincronizarRelogio);
  configTime(0, 0, "pool.ntp.org", "time.google.com");
}


bool relogioOk() {

  if (SIMULAR_SEM_RELOGIO_S > 0 && millis() < SIMULAR_SEM_RELOGIO_S * 1000UL) {
    return false;
  }

  return relogioSincronizado && time(nullptr) >= EPOCH_VALIDO;
}


// ==========================================================
// CONEXAO
// ==========================================================

bool conexaoDisponivel() {

  if (SIMULAR_QUEDA_S > 0 && millis() >= SIMULAR_QUEDA_INICIO_S * 1000UL &&
      millis() < (SIMULAR_QUEDA_INICIO_S + SIMULAR_QUEDA_S) * 1000UL) {
    return false;
  }

  return WiFi.status() == WL_CONNECTED;
}


// ==========================================================
// FILA EM FLASH (STORE-AND-FORWARD)
// ==========================================================
//
// Uma linha JSON por leitura, da mais antiga para a mais nova. O loop grava
// no fim (enfileirar); a tarefa de envio le o inicio e apaga o que a nuvem
// confirmou (descartarEnviadas). TravaFila em toda funcao que abre o arquivo.

int contarFila() {

  TravaFila trava;

  File arquivo = LittleFS.open(FILA_ARQUIVO, "r");

  if (!arquivo) {
    return 0;
  }

  int linhas = 0;

  while (arquivo.available()) {

    String linha = arquivo.readStringUntil('\n');
    linha.trim();

    if (linha.length() > 0) {
      linhas++;
    }
  }

  arquivo.close();

  return linhas;
}


// Reescreve a fila pulando as `pular` primeiras linhas (fila cheia).
void descartarInicioDaFila(int pular) {

  TravaFila trava;

  File origem = LittleFS.open(FILA_ARQUIVO, "r");
  File destino = LittleFS.open("/fila.tmp", "w");

  int indice = 0;
  int restantes = 0;

  while (origem && origem.available()) {

    String linha = origem.readStringUntil('\n');
    linha.trim();

    if (linha.length() == 0) {
      continue;
    }

    if (indice++ >= pular) {
      destino.println(linha);
      restantes++;
    }
  }

  if (origem) {
    origem.close();
  }

  destino.close();

  LittleFS.remove(FILA_ARQUIVO);
  LittleFS.rename("/fila.tmp", FILA_ARQUIVO);

  filaTamanho = restantes;
}


// Reescreve a fila sem as linhas que a nuvem confirmou. Compara pelo texto
// (cada linha tem seu seq): se o loop gravou linha nova, ou a fila cheia
// descartou a mais antiga, no meio do envio, nada que nao saiu e apagado.
void descartarEnviadas(const String lote[], const bool enviada[], int quantas) {

  TravaFila trava;

  bool tirada[REENVIO_POR_LOTE] = { false };

  File origem = LittleFS.open(FILA_ARQUIVO, "r");

  if (!origem) {
    filaTamanho = 0;
    return;
  }

  File destino = LittleFS.open("/fila.tmp", "w");

  int restantes = 0;

  while (origem.available()) {

    String linha = origem.readStringUntil('\n');
    linha.trim();

    if (linha.length() == 0) {
      continue;
    }

    bool pular = false;

    for (int i = 0; i < quantas; i++) {
      if (enviada[i] && !tirada[i] && linha == lote[i]) {
        tirada[i] = true;
        pular = true;
        break;
      }
    }

    if (!pular) {
      destino.println(linha);
      restantes++;
    }
  }

  origem.close();
  destino.close();

  LittleFS.remove(FILA_ARQUIVO);
  LittleFS.rename("/fila.tmp", FILA_ARQUIVO);

  filaTamanho = restantes;
}


// Linhas guardadas sem relogio levam "ms" (millis da medicao) no lugar do medidoEm.
volatile bool filaTemMs = false;


bool linhaTemMs(const String &linha) {

  return linha.indexOf("\"ms\":") >= 0;
}


// Reescreve a fila tratando as linhas com "ms":
//   converter = true: troca "ms" pelo medidoEm (agora - tempo desde a medicao);
//   converter = false: descarta (vieram de antes de um reinicio, o millis zerou).
void reescreverFilaMs(bool converter) {

  TravaFila trava;

  File origem = LittleFS.open(FILA_ARQUIVO, "r");

  if (!origem) {
    filaTemMs = false;
    return;
  }

  File destino = LittleFS.open("/fila.tmp", "w");

  int mantidas = 0, convertidas = 0, descartadas = 0;
  time_t agora = time(nullptr);
  unsigned long agoraMs = millis();

  while (origem.available()) {

    String linha = origem.readStringUntil('\n');
    linha.trim();

    if (linha.length() == 0) {
      continue;
    }

    if (linhaTemMs(linha)) {

      int pos = linha.indexOf(",\"ms\":");
      unsigned long ms = strtoul(linha.c_str() + pos + 6, nullptr, 10);

      if (!converter || pos < 0 || ms > agoraMs) {
        descartadas++;
        continue;
      }

      long long medido = (long long)agora - (long long)((agoraMs - ms) / 1000);
      int fim = linha.indexOf('}', pos);

      linha = linha.substring(0, pos) + ",\"medidoEm\":" + String(medido) + linha.substring(fim);
      convertidas++;
    }

    destino.println(linha);
    mantidas++;
  }

  origem.close();
  destino.close();

  LittleFS.remove(FILA_ARQUIVO);
  LittleFS.rename("/fila.tmp", FILA_ARQUIVO);

  filaTamanho = mantidas;
  filaTemMs = false;

  if (convertidas > 0) {
    Serial.print("FILA: relogio sincronizado, ");
    Serial.print(convertidas);
    Serial.println(" leituras sem horario ganharam o horario da medicao.");
  }

  if (descartadas > 0) {
    Serial.print("FILA: ");
    Serial.print(descartadas);
    Serial.println(" leituras sem horario descartadas (a placa reiniciou antes de acertar o relogio).");
  }
}


// Procura linhas com "ms" (so no boot; depois o flag acompanha).
bool filaTemLinhaMs() {

  TravaFila trava;

  File arquivo = LittleFS.open(FILA_ARQUIVO, "r");

  if (!arquivo) {
    return false;
  }

  bool achou = false;

  while (arquivo.available() && !achou) {
    achou = linhaTemMs(arquivo.readStringUntil('\n'));
  }

  arquivo.close();

  return achou;
}


// Grava uma linha no fim da fila. false = flash indisponivel.
bool enfileirar(const char *payload, bool offline) {

  TravaFila trava;

  File arquivo = LittleFS.open(FILA_ARQUIVO, "a");

  if (!arquivo) {

    Serial.println("FILA: erro ao abrir a flash.");
    return false;
  }

  arquivo.println(payload);
  arquivo.close();

  filaTamanho++;

  if (filaTamanho > FILA_MAX) {

    Serial.println("FILA: cheia, descartando a leitura mais antiga.");
    descartarInicioDaFila(filaTamanho - FILA_MAX);
  }

  Serial.print(offline ? "FILA: leitura guardada offline (" : "FILA: leitura guardada antes do envio (");
  Serial.print(filaTamanho);
  Serial.println(" na fila).");

  return true;
}


// Guarda a leitura na fila (com ou sem rede: o envio sai da fila). Sem
// relogio, guarda o millis da medicao. false = flash indisponivel.
bool guardarLeitura(const char *payload, time_t medidoEm, unsigned long msMedicao, bool offline) {

  if (medidoEm > 0) {
    return enfileirar(payload, offline);
  }

  String linha = payload;
  int fim = linha.lastIndexOf('}');

  linha = linha.substring(0, fim) + ",\"ms\":" + String(msMedicao) + "}";

  Serial.println("FILA: sem relogio; guardando com o tempo desde que a placa ligou.");

  TravaFila trava;

  bool ok = enfileirar(linha.c_str(), offline);

  if (ok) {
    filaTemMs = true;
  }

  return ok;
}


// Flash indisponivel: a leitura do ciclo vai direto, uma tentativa so.
portMUX_TYPE envioDiretoTrava = portMUX_INITIALIZER_UNLOCKED;
char envioDireto[160];
bool envioDiretoPendente = false;


void pedirEnvioDireto(const char *payload) {

  portENTER_CRITICAL(&envioDiretoTrava);
  strncpy(envioDireto, payload, sizeof(envioDireto) - 1);
  envioDireto[sizeof(envioDireto) - 1] = '\0';
  envioDiretoPendente = true;
  portEXIT_CRITICAL(&envioDiretoTrava);
}


void registrarResultado(int status) {

  indUltimoHttp = status;

  if (status == 201 || status == 200) {
    indEnviadoEm = millis();
  }
}


void enviarDireto() {

  char copia[160];
  bool tem;

  portENTER_CRITICAL(&envioDiretoTrava);
  tem = envioDiretoPendente;
  if (tem) {
    memcpy(copia, envioDireto, sizeof(copia));
    envioDiretoPendente = false;
  }
  portEXIT_CRITICAL(&envioDiretoTrava);

  if (!tem) {
    return;
  }

  Serial.println("Enviando telemetria ao Azure (sem fila: flash indisponivel)...");
  alimentarWatchdog();
  registrarResultado(postarAzure(copia));
}


// Envia as leituras da fila, da mais antiga para a mais nova, ate esvaziar ou
// ate a primeira falha temporaria (para manter a ordem). Roda na tarefa de
// envio. A trava da fila fica presa so para ler e para reescrever o arquivo,
// nunca durante a requisicao: o loop grava a leitura nova sem esperar a rede.
void reenviarFila() {

  if (filaTamanho == 0) {
    return;
  }

  if (filaTemMs && relogioOk()) {
    reescreverFilaMs(true);
  }

  // Aviso de espera pelo relogio: uma vez so, ate o relogio chegar.
  static bool avisouRelogio = false;

  if (relogioOk()) {
    avisouRelogio = false;
  }

  // Limite de voltas: protege contra reenviar sem fim se o descarte falhar.
  for (int volta = 0; volta <= FILA_MAX / REENVIO_POR_LOTE &&
                      filaTamanho > 0 && !pausaEnvio && conexaoDisponivel(); volta++) {

    String lote[REENVIO_POR_LOTE];
    bool enviada[REENVIO_POR_LOTE] = { false };
    int lidas = 0;
    int pendentes = 0;

    {
      TravaFila trava;

      File arquivo = LittleFS.open(FILA_ARQUIVO, "r");

      if (!arquivo) {
        filaTamanho = 0;
        return;
      }

      while (arquivo.available() && lidas < REENVIO_POR_LOTE) {

        String linha = arquivo.readStringUntil('\n');
        linha.trim();

        if (linha.length() > 0) {
          lote[lidas++] = linha;
        }
      }

      arquivo.close();
      pendentes = filaTamanho;
    }

    if (lidas == 0) {
      break;
    }

    int enviadas = 0;
    bool avisouEnvio = false;
    bool falhou = false;

    for (int i = 0; i < lidas && !pausaEnvio; i++) {

      String corpo = lote[i];
      unsigned long ms = 0;
      std::string semMs;

      // Sem relogio ainda: recente sai sem medidoEm (a nuvem usa a hora da
      // chegada); mais velha espera o NTP (reescreverFilaMs da o horario).
      if (linhaComMsCore(lote[i].c_str(), &ms, &semMs)) {

        if (millis() - ms > SEM_RELOGIO_RECENTE_MS) {
          if (!avisouRelogio) {
            Serial.println("FILA: aguardando o relogio para reenviar leituras sem horario.");
            avisouRelogio = true;
          }
          continue;
        }

        corpo = semMs.c_str();
      }

      alimentarWatchdog();

      if (!avisouEnvio) {
        Serial.print("Enviando telemetria ao Azure (");
        Serial.print(pendentes);
        Serial.println(" na fila)...");
        avisouEnvio = true;
      }

      Serial.print("FILA: enviando ");
      Serial.println(corpo);

      int status = postarAzure(corpo.c_str());
      registrarResultado(status);

      if (falhaTemporaria(status)) {
        falhou = true;
        break;
      }

      // Enviada, ou recusada de vez (4xx): nao adianta reenviar.
      enviada[i] = true;
      enviadas++;
    }

    if (enviadas > 0) {

      descartarEnviadas(lote, enviada, lidas);

      Serial.print("FILA: ");
      Serial.print(enviadas);
      Serial.print(" reenviadas, ");
      Serial.print(filaTamanho);
      Serial.println(" restantes.");
    }

    if (falhou || enviadas == 0) {
      break;
    }
  }
}


// ==========================================================
// TAREFA DE ENVIO
// ==========================================================

#define TAREFA_ENVIO_PILHA 12288   // bytes; TLS (mbedTLS) + HTTPClient
#define TAREFA_ENVIO_ESPERA_MS 1000


void tarefaEnvio(void *parametro) {

  esp_task_wdt_add(NULL);

  for (;;) {

    esp_task_wdt_reset();

    // Acorda quando o loop grava uma leitura, ou a cada 1 s (fila antiga,
    // rede que voltou, keep-alive do MQTT).
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(TAREFA_ENVIO_ESPERA_MS));

    esp_task_wdt_reset();

    if (pausaEnvio || !conexaoDisponivel()) {
      continue;
    }

#ifdef COM_MQTT
    // Mantem a conexao viva (PINGREQ) e processa o que o broker mandar.
    mqtt.loop();
#endif

    // Heartbeat velho nao diz nada sobre agora: so vale o do ultimo ciclo.
    bool heartbeat = heartbeatPendente;
    if (heartbeat && millis() - heartbeatPedidoEm > INTERVALO_ENVIO) {
      heartbeatPendente = false;
      heartbeat = false;
    }

    if (filaTamanho > 0 || heartbeat || envioDiretoPendente) {

      indEnviando = true;

      // Primeiro o que ficou guardado, para manter a ordem no banco.
      reenviarFila();
      enviarDireto();

      if (heartbeat && !pausaEnvio && conexaoDisponivel()) {
        heartbeatPendente = false;
        esp_task_wdt_reset();
        indUltimoHttp = enviarHeartbeat("sensor_falha");
      }

      indEnviando = false;
    }

#ifdef COM_MQTT
    LeituraMqtt leitura;

    portENTER_CRITICAL(&mqttLeituraTrava);
    leitura = leituraMqtt;
    leituraMqtt.pendente = false;
    portEXIT_CRITICAL(&mqttLeituraTrava);

    // So a leitura deste ciclo (a fila offline e so do HTTPS).
    if (leitura.pendente && millis() - leitura.em < INTERVALO_ENVIO && !pausaEnvio) {
      esp_task_wdt_reset();
      publicarMqtt(leitura.temperatura, leitura.umidade, leitura.rssi);
    }
#endif
  }
}


void iniciarTarefaEnvio() {

  if (xTaskCreate(tarefaEnvio, "envio", TAREFA_ENVIO_PILHA, nullptr, 1, &tarefaEnvioHandle) != pdPASS) {
    Serial.println("ENVIO: sem memoria para a tarefa de envio; nada sera enviado.");
    tarefaEnvioHandle = nullptr;
  }
}


// ==========================================================
// CONFIGURACAO PELO CABO (protocolo com o painel)
// ==========================================================
//
// Uma linha JSON por mensagem. Painel -> placa comeca com "CT<",
// placa -> painel com "CT>"; o resto da serial e log comum.
//
//   CT<{"cmd":"info"}
//   CT<{"cmd":"wifi","ssid":"..","senha":".."}                      troca so a rede
//   CT<{"cmd":"config","ssid":"..","senha":"..","id":"..","chave":".."}
//   CT<{"cmd":"redes"}                                              redes 2.4 GHz vistas
//
// A placa testa a rede antes de gravar e responde
//   CT>{"ok":true,"wifi":"conectado","rssi":-55,"canal":6,"seguranca":"wpa2","id":".."}
//   CT>{"ok":false,"erro":"..","motivo":15,"rssi":-84,"canal":6,"seguranca":"wpa2"}
// erro: senha | rede_nao_encontrada | rede_corporativa | seguranca_incompativel |
//       sinal_fraco | sem_ip | tempo | rede_invalida | ...; motivo = codigo do
//       driver (wifi_err_reason_t); rssi/canal/seguranca so quando o scan achou a rede.
//   CT>{"ok":true,"redes":[{"ssid":"..","rssi":-60,"canal":6,"seguranca":"wpa2"}]}
//   CT>{"pronto":true,"fw":".."}     uma vez, ao fim do setup (placa pronta para comandos)
// Senha e chave nunca voltam pela serial nem aparecem no log.

String bufferSerial;
String comandoPendente;


// Junta os bytes da serial; true quando chega um comando completo.
bool lerSerial() {

  while (Serial.available()) {

    char c = Serial.read();

    if (c == '\r') {
      continue;
    }

    if (c != '\n') {

      if (bufferSerial.length() < 512) {
        bufferSerial += c;
      }
      continue;
    }

    String linha = bufferSerial;
    bufferSerial = "";
    linha.trim();

    if (linha.startsWith("CT<")) {
      comandoPendente = linha.substring(3);
      return true;
    }
  }

  return comandoPendente.length() > 0;
}


// Le o texto de "chave":"valor" no JSON, desfazendo os escapes basicos.
String textoDoJson(const String &json, const char *chave) {

  String alvo = String("\"") + chave + "\"";
  int pos = json.indexOf(alvo);

  if (pos < 0) {
    return "";
  }

  pos = json.indexOf(':', pos + alvo.length());
  if (pos < 0) {
    return "";
  }

  pos = json.indexOf('"', pos);
  if (pos < 0) {
    return "";
  }

  String valor;

  for (int i = pos + 1; i < (int)json.length(); i++) {

    char c = json[i];

    if (c == '"') {
      return valor;
    }

    if (c == '\\' && i + 1 < (int)json.length()) {

      char proximo = json[++i];

      if (proximo == 'n') {
        valor += '\n';
      } else if (proximo == 't') {
        valor += '\t';
      } else {
        valor += proximo;   // \" \\ \/
      }
      continue;
    }

    valor += c;
  }

  return "";   // sem aspas de fechamento: JSON cortado
}


// Escreve um texto como string JSON (com aspas e escapes).
String emJson(const String &texto) {

  String saida = "\"";

  for (int i = 0; i < (int)texto.length(); i++) {

    char c = texto[i];

    if (c == '"' || c == '\\') {
      saida += '\\';
    }

    if ((unsigned char)c >= 0x20) {
      saida += c;
    }
  }

  return saida + "\"";
}


void responder(const String &json) {

  Serial.print("CT>");
  Serial.println(json);
}


void aoCairWiFi(WiFiEvent_t evento, WiFiEventInfo_t info) {

  associou = false;

  // ASSOC_LEAVE e STA_LEAVING vem do disconnect da propria placa: nao e falha.
  uint8_t motivo = info.wifi_sta_disconnected.reason;

  if (motivo != WIFI_REASON_ASSOC_LEAVE && motivo != WIFI_REASON_STA_LEAVING) {
    motivoQueda = info.wifi_sta_disconnected.reason;
  }
}


void aoAssociarWiFi(WiFiEvent_t evento, WiFiEventInfo_t info) {

  associou = true;
}


// Nome curto do tipo de seguranca do AP, como vai para o painel.
const char *nomeSeguranca(wifi_auth_mode_t modo) {

  switch (modo) {
    case WIFI_AUTH_OPEN:                 return "aberta";
    case WIFI_AUTH_WEP:                  return "wep";
    case WIFI_AUTH_WPA_PSK:              return "wpa";
    case WIFI_AUTH_WPA2_PSK:             return "wpa2";
    case WIFI_AUTH_WPA_WPA2_PSK:         return "wpa_wpa2";
    case WIFI_AUTH_WPA3_PSK:             return "wpa3";
    case WIFI_AUTH_WPA2_WPA3_PSK:        return "wpa2_wpa3";
    case WIFI_AUTH_OWE:                  return "owe";
    case WIFI_AUTH_WPA_ENTERPRISE:
    case WIFI_AUTH_WPA2_ENTERPRISE:
    case WIFI_AUTH_WPA3_ENTERPRISE:
    case WIFI_AUTH_WPA2_WPA3_ENTERPRISE:
    case WIFI_AUTH_WPA3_ENT_192:         return "enterprise";
    default:                             return "outra";
  }
}


// WPA-Enterprise (802.1X, login com usuario): a placa so tem SSID e senha.
bool redeCorporativa(wifi_auth_mode_t modo) {

  return modo == WIFI_AUTH_WPA_ENTERPRISE || modo == WIFI_AUTH_WPA2_ENTERPRISE ||
         modo == WIFI_AUTH_WPA3_ENTERPRISE || modo == WIFI_AUTH_WPA2_WPA3_ENTERPRISE ||
         modo == WIFI_AUTH_WPA3_ENT_192;
}


// Scan bloqueante. O driver recusa o scan enquanto a estacao esta no meio de
// uma tentativa de conexao (logo depois do boot, por exemplo): nesse caso
// para a tentativa, espera o estado assentar e repete, ate SCAN_TENTATIVAS.
int16_t escanear(const char *ssid) {

  int16_t n = WIFI_SCAN_FAILED;

  for (int tentativa = 1; tentativa <= SCAN_TENTATIVAS; tentativa++) {

    n = WiFi.scanNetworks(false, true, false, 300, 0, ssid);

    if (n >= 0) {
      return n;
    }

    Serial.printf("WIFI: scan recusado (%d), tentativa %d de %d.\n", n, tentativa, SCAN_TENTATIVAS);
    WiFi.scanDelete();

    if (tentativa == SCAN_TENTATIVAS) {
      break;
    }

    if (WiFi.status() != WL_CONNECTED) {
      WiFi.disconnect();
      ultimaTentativaWiFi = 0;   // o loop reconecta logo depois
    }

    // Espera crescente, alimentando o watchdog, para o driver sair do "connecting".
    unsigned long inicio = millis();
    while (millis() - inicio < SCAN_ESPERA_MS * (unsigned long)tentativa) {
      esperarAtualizando(50);
      alimentarWatchdog();
    }
  }

  return n;
}


// Scan dirigido ao nome (acha tambem rede oculta), guardando o AP de sinal
// mais forte. O ESP32-C3 so tem radio 2.4 GHz: rede so 5 GHz nao aparece.
// Resultado em ultimoAp (o Arduino nao aceita a struct no prototipo gerado).
void procurarRede(const String &ssid) {

  ApVisto &ap = ultimoAp;
  ap = { false, false, 0, 0, WIFI_AUTH_OPEN };

  int16_t n = escanear(ssid.c_str());

  if (n < 0) {
    Serial.printf("WIFI: scan falhou (%d); testando sem ele.\n", n);
    return;
  }

  ap.escaneou = true;

  for (int i = 0; i < n; i++) {

    if (WiFi.SSID(i) != ssid) {
      continue;
    }

    if (!ap.achou || WiFi.RSSI(i) > ap.rssi) {
      ap.achou = true;
      ap.rssi = WiFi.RSSI(i);
      ap.canal = WiFi.channel(i);
      ap.seguranca = WiFi.encryptionType(i);
    }
  }

  WiFi.scanDelete();

  if (ap.achou) {
    Serial.printf("WIFI: rede achada no canal %ld, sinal %ld dBm, seguranca %s.\n",
                  (long)ap.canal, (long)ap.rssi, nomeSeguranca(ap.seguranca));
  } else {
    Serial.println("WIFI: rede nao apareceu no scan 2.4 GHz.");
  }
}


// Codigo de erro para o painel a partir do motivo do driver ("" = sem
// conclusao). Handshake que estoura com sinal fraco e sinal, nao senha.
String traduzirMotivo(uint8_t motivo) {

  bool sinalFraco = ultimoAp.achou && ultimoAp.rssi < RSSI_FRACO;

  switch (motivo) {

    case WIFI_REASON_NO_AP_FOUND:
    case WIFI_REASON_NO_AP_FOUND_IN_RSSI_THRESHOLD:
      return "rede_nao_encontrada";

    case WIFI_REASON_NO_AP_FOUND_W_COMPATIBLE_SECURITY:
    case WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD:
      return "seguranca_incompativel";

    case WIFI_REASON_802_1X_AUTH_FAILED:
      return "rede_corporativa";

    case WIFI_REASON_BEACON_TIMEOUT:
      return "sinal_fraco";

    case WIFI_REASON_AUTH_EXPIRE:
    case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_HANDSHAKE_TIMEOUT:
      return sinalFraco ? "sinal_fraco" : "senha";

    case WIFI_REASON_AUTH_FAIL:
    case WIFI_REASON_MIC_FAILURE:
      return "senha";
  }

  return "";
}


// Erro que nao melhora esperando mais (o sinal fraco pode passar na proxima tentativa).
bool erroDefinitivo(const String &erro) {

  return erro.length() > 0 && erro != "sinal_fraco";
}


// Tenta a rede; devolve "" se conectou ou o motivo da falha. Rede aberta
// zera a senha (com senha o driver exige WPA2 e nao acha a rede).
String testarWiFi(const String &ssid, String &senha) {

  WiFi.disconnect();
  delay(200);

  motivoQueda = 0;
  procurarRede(ssid);

  if (ultimoAp.escaneou && !ultimoAp.achou) {
    return "rede_nao_encontrada";
  }

  if (ultimoAp.achou) {

    if (redeCorporativa(ultimoAp.seguranca)) {
      return "rede_corporativa";
    }

    if (ultimoAp.seguranca == WIFI_AUTH_WEP || ultimoAp.seguranca == WIFI_AUTH_WPA_PSK) {
      return "seguranca_incompativel";
    }

    bool aberta = ultimoAp.seguranca == WIFI_AUTH_OPEN || ultimoAp.seguranca == WIFI_AUTH_OWE;

    if (aberta) {
      senha = "";
    } else if (senha.length() == 0) {
      return "senha";
    }
  }

  iniciarWiFi(ssid.c_str(), senha.c_str());

  unsigned long limite = ultimoAp.achou ? TESTE_WIFI_ACHADA_MS : TESTE_WIFI_MS;
  unsigned long inicio = millis();
  wl_status_t status = WiFi.status();

  while (millis() - inicio < limite) {

    status = WiFi.status();

    if (status == WL_CONNECTED || status == WL_CONNECT_FAILED ||
        status == WL_NO_SSID_AVAIL) {
      break;
    }

    // O driver ja disse por que caiu: nao precisa esperar o tempo todo.
    if (erroDefinitivo(traduzirMotivo(motivoQueda)) && millis() - inicio > 3000) {
      break;
    }

    esperarAtualizando(250);
    alimentarWatchdog();
  }

  logMotivo("teste da rede");

  if (status == WL_CONNECTED) {
    return "";
  }

  String motivo = traduzirMotivo(motivoQueda);

  if (motivo.length() > 0) {
    return motivo;
  }

  if (status == WL_NO_SSID_AVAIL) {
    return "rede_nao_encontrada";
  }

  if (status == WL_CONNECT_FAILED) {
    return "senha";
  }

  // Associou (WPA ok) mas o DHCP nao deu endereco no tempo.
  if (associou) {
    return "sem_ip";
  }

  return "tempo";
}


// Sinal, canal e seguranca do AP visto no scan, para a resposta CT>.
String dadosDoAp() {

  if (!ultimoAp.achou) {
    return "";
  }

  return String(",\"rssi\":") + ultimoAp.rssi + ",\"canal\":" + ultimoAp.canal +
         ",\"seguranca\":\"" + nomeSeguranca(ultimoAp.seguranca) + "\"";
}


// CT<{"cmd":"redes"}: redes 2.4 GHz que a placa enxerga, uma por nome (o AP
// de sinal mais forte), da mais forte para a mais fraca. Nenhuma senha.
void listarRedes() {

  Serial.println("REDES: procurando redes 2.4 GHz...");

  int16_t n = escanear(nullptr);

  if (n < 0) {
    Serial.printf("REDES: scan falhou (%d).\n", n);
    responder("{\"ok\":false,\"erro\":\"scan_falhou\"}");
    return;
  }

  const int MAX_VISTAS = 64;
  int ordem[MAX_VISTAS];
  int total = 0;

  for (int i = 0; i < n && i < MAX_VISTAS; i++) {

    String nome = WiFi.SSID(i);

    if (nome.length() == 0) {
      continue;   // rede oculta: sem nome para mostrar
    }

    // Mesmo nome ja listado: fica o AP de sinal mais forte.
    int repetida = -1;
    for (int j = 0; j < total; j++) {
      if (WiFi.SSID(ordem[j]) == nome) {
        repetida = j;
        break;
      }
    }

    if (repetida >= 0) {
      if (WiFi.RSSI(i) > WiFi.RSSI(ordem[repetida])) {
        ordem[repetida] = i;
      }
      continue;
    }

    ordem[total++] = i;
  }

  // Ordena pelo sinal (insercao; sao poucas).
  for (int i = 1; i < total; i++) {
    int atual = ordem[i];
    int j = i - 1;
    while (j >= 0 && WiFi.RSSI(ordem[j]) < WiFi.RSSI(atual)) {
      ordem[j + 1] = ordem[j];
      j--;
    }
    ordem[j + 1] = atual;
  }

  String json = "{\"ok\":true,\"redes\":[";

  for (int k = 0; k < total && k < REDES_MAX; k++) {

    int i = ordem[k];

    if (k > 0) {
      json += ",";
    }

    json += String("{\"ssid\":") + emJson(WiFi.SSID(i)) + ",\"rssi\":" + WiFi.RSSI(i) +
            ",\"canal\":" + WiFi.channel(i) + ",\"seguranca\":\"" +
            nomeSeguranca(WiFi.encryptionType(i)) + "\"}";
  }

  json += "]}";

  WiFi.scanDelete();

  Serial.printf("REDES: %d rede(s) vista(s), %d na resposta.\n", total, min(total, REDES_MAX));
  responder(json);
}


void apagarFila() {

  TravaFila trava;

  LittleFS.remove(FILA_ARQUIVO);
  filaTamanho = 0;
  filaTemMs = false;
}


// Resultado do comando de rede na tela (fica CABO_RESULTADO_MS).
void mostrarResultadoCabo(const String &erro) {

  indCabo = CABO_RESULTADO;
  indCaboResultado = resumoCabo(erro);
  indCaboEm = millis();
  desenharIndicadores();
}


void tratarComando() {

  String cmd = comandoPendente;
  comandoPendente = "";

  String tipo = textoDoJson(cmd, "cmd");

  if (tipo == "info") {

    responder(String("{\"id\":") + emJson(cfgId.length() ? cfgId : idDoChip()) +
              ",\"chip\":" + emJson(idDoChip()) +
              ",\"configurado\":" + (temIdentidade() ? "true" : "false") +
              ",\"ssid\":" + emJson(cfgSsid) +
              ",\"wifi\":" + (WiFi.status() == WL_CONNECTED ? "true" : "false") +
              ",\"fw\":" + emJson(FW_VERSAO) + "}");
    return;
  }

  if (tipo == "redes") {

    listarRedes();
    return;
  }

  if (tipo != "wifi" && tipo != "config") {

    responder("{\"ok\":false,\"erro\":\"comando_desconhecido\"}");
    return;
  }

  String ssid = textoDoJson(cmd, "ssid");
  String senha = textoDoJson(cmd, "senha");
  String id = textoDoJson(cmd, "id");
  String chave = textoDoJson(cmd, "chave");

  if (ssid.length() == 0 || ssid.length() > 32 || senha.length() > 63) {

    responder("{\"ok\":false,\"erro\":\"rede_invalida\"}");
    mostrarResultadoCabo("rede_invalida");
    return;
  }

  if (tipo == "wifi" && !temIdentidade()) {

    responder("{\"ok\":false,\"erro\":\"sem_identidade\"}");
    mostrarResultadoCabo("sem_identidade");
    return;
  }

  if (tipo == "config" && (id.length() < 3 || id.length() > 40 || chave.length() < 16)) {

    responder("{\"ok\":false,\"erro\":\"identidade_invalida\"}");
    mostrarResultadoCabo("identidade_invalida");
    return;
  }

  Serial.print("CONFIG: testando a rede ");
  Serial.println(ssid);

  // A tarefa de envio para enquanto a rede e a identidade mudam (a requisicao
  // em curso cai junto com o Wi-Fi e a leitura segue na fila).
  pausaEnvio = true;

  indCabo = CABO_TESTANDO;
  indCaboSsid = ssid;
  desenharIndicadores();

  String erro = testarWiFi(ssid, senha);

  mostrarResultadoCabo(erro);

  if (erro.length() > 0) {

    Serial.print("CONFIG: falhou (");
    Serial.print(erro);
    Serial.print("). Motivo do Wi-Fi: ");
    Serial.print(motivoQueda);
    if (motivoQueda > 0) {
      Serial.print(" (");
      Serial.print(WiFi.disconnectReasonName((wifi_err_reason_t)motivoQueda));
      Serial.print(")");
    }
    Serial.println(". Nada foi gravado; voltando para a rede anterior.");

    responder("{\"ok\":false,\"erro\":\"" + erro + "\",\"motivo\":" + String(motivoQueda) +
              dadosDoAp() + "}");

    if (cfgSsid.length() > 0) {
      iniciarWiFi(cfgSsid.c_str(), cfgSenha.c_str());
    } else {
      WiFi.disconnect();
    }
    pausaEnvio = false;
    return;
  }

  // Conectou: so agora grava na flash.
  preferencias.begin("config", false);
  preferencias.putString("ssid", ssid);
  preferencias.putString("senha", senha);

  if (tipo == "config") {

    // Leituras guardadas eram da identidade anterior: a nuvem recusaria.
    if (id != cfgId) {
      apagarFila();
    }

    preferencias.putString("id", id);
    preferencias.putString("chave", chave);
    xSemaphoreTake(cfgTrava, portMAX_DELAY);
    cfgId = id;
    cfgChave = chave;
    xSemaphoreGive(cfgTrava);
  }

  preferencias.end();

  cfgSsid = ssid;
  cfgSenha = senha;

  Serial.print("CONFIG: gravado. Sensor ");
  Serial.print(cfgId);
  Serial.print(" na rede ");
  Serial.println(cfgSsid);

  String seguranca = ultimoAp.achou ? String(",\"seguranca\":\"") + nomeSeguranca(ultimoAp.seguranca) + "\"" : "";

  responder(String("{\"ok\":true,\"wifi\":\"conectado\",\"rssi\":") + WiFi.RSSI() +
            ",\"canal\":" + WiFi.channel() + seguranca + ",\"id\":" + emJson(cfgId) + "}");

  sincronizarRelogio();

  pausaEnvio = false;

  // Proxima leitura sai ja, para o painel mostrar "online" logo.
  cicloImediato = true;
}


// ==========================================================
// SETUP
// ==========================================================

void setup() {

  // Comando de configuracao passa de 200 bytes; o buffer padrao e pequeno.
  Serial.setRxBufferSize(1024);
  Serial.begin(115200);

#if ARDUINO_USB_CDC_ON_BOOT && ARDUINO_USB_MODE
  // USB nativo (placa fisica): porta que ninguem le nao segura o firmware.
  Serial.setTxTimeoutMs(SERIAL_TX_TIMEOUT_MS);
#endif

  filaTrava = xSemaphoreCreateRecursiveMutex();
  cfgTrava = xSemaphoreCreateMutex();

  iniciarWatchdog();

  indReinicioWdt = reiniciouPorWatchdog();

#ifdef TELA_OLED
  Wire.begin(TELA_SDA, TELA_SCL);
  tela.begin();
  tela.setContrast(255);
#else
  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_AMARELO, OUTPUT);
  pinMode(LED_VERMELHO, OUTPUT);
#endif

#if defined(LED_PLACA) && !defined(LED_PLACA_RGB)
  pinMode(LED_PLACA, OUTPUT);
#endif

  // INICIANDO na tela e LEDs em sequencia desde o primeiro segundo.
  esperarAtualizando(1000);

#ifdef TESTE_DHT
  autotesteDht();
#endif

  Serial.println();
  Serial.println("========================================");
  Serial.println("          COLDTRACK EDGE");
  Serial.println(" Monitoramento Transporte Refrigerado");
  Serial.println("========================================");

  // true = formata a flash se ainda nao tiver sistema de arquivos.
  if (!LittleFS.begin(true)) {
    Serial.println("FILA: flash indisponivel. Leituras offline serao perdidas.");
  }

  filaTamanho = contarFila();

  // Linha sem horario de antes deste boot nao tem mais referencia (millis zerou).
  if (filaTemLinhaMs()) {
    reescreverFilaMs(false);
  }

  carregarFaixa();

  carregarSeq();

  carregarConfig();

  // Modo estacao antes de tudo: o MAC (ID sugerido) so aparece com o radio ligado.
  WiFi.mode(WIFI_STA);
  WiFi.onEvent(aoCairWiFi, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  WiFi.onEvent(aoAssociarWiFi, ARDUINO_EVENT_WIFI_STA_CONNECTED);

  Serial.print("SENSOR: ");
  Serial.print(temIdentidade() ? cfgId : String("sem identidade (chip ") + idDoChip() + ")");
  Serial.print(" | firmware ");
  Serial.println(FW_VERSAO);

  Serial.print("FILA: ");
  Serial.print(filaTamanho);
  Serial.println(" leituras pendentes na flash.");

  Serial.print("SEQ: ultima leitura numerada ");
  Serial.println(seqAtual);

  if (reiniciouPorWatchdog()) {
    Serial.println("WATCHDOG: placa reiniciada por travamento; retomando fila e sequencia.");
  }

  conectarWiFi();

  sincronizarRelogio();

  iniciarTarefaEnvio();

  Serial.println();
  Serial.println("Sistema iniciado.");

  indIniciando = false;
  desenharIndicadores();

  // Linha de prontidao: o painel espera por ela (ou por um "info" respondido)
  // antes de mandar comandos, porque abrir a porta pode reiniciar a placa.
  responder(String("{\"pronto\":true,\"fw\":") + emJson(FW_VERSAO) + "}");
}


// ==========================================================
// LOOP
// ==========================================================

void loop() {

  alimentarWatchdog();

  atualizarIndicadores();

  // Teste do watchdog: para de alimentar e espera o reinicio.
  if (SIMULAR_TRAVAMENTO_S > 0 && millis() > SIMULAR_TRAVAMENTO_S * 1000UL &&
      !reiniciouPorWatchdog()) {
    Serial.println("TESTE: loop travado de proposito; o watchdog deve reiniciar a placa.");
    while (true) {
      delay(1000);
    }
  }

  // --------------------------------------------------------
  // Configuracao chegando pelo cabo
  // --------------------------------------------------------

  if (lerSerial()) {
    tratarComando();
  }


  // --------------------------------------------------------
  // Sem Wi-Fi ou sem ID/chave: pisca o amarelo e espera o cabo
  // --------------------------------------------------------

  if (cfgSsid.length() == 0 || !temIdentidade()) {

    static unsigned long ultimoAviso = 0;

#ifdef TELA_OLED
    // Sem rede a tela segue mostrando o sensor, com o aviso de configurar.
    static unsigned long ultimaLeitura = 0;
    if (millis() - ultimaLeitura >= 3000 || ultimaLeitura == 0) {
      ultimaLeitura = millis();
      lerSensor(&indTemperatura, &indUmidade);
    }
#endif
    // LED: amarelo em dois toques (atualizarIndicadores).

    if (millis() - ultimoAviso >= 10000 || ultimoAviso == 0) {

      ultimoAviso = millis();
      Serial.println("Aguardando configuracao pelo cabo (painel > Sensores > Conectar sensor pelo cabo).");
    }

    delay(20);
    return;
  }


  // --------------------------------------------------------
  // Verifica conexão Wi-Fi
  // --------------------------------------------------------

  // Uma tentativa nova a cada RECONEXAO_MS, sem esperar por ela: no meio
  // delas o driver segue tentando sozinho, e a medicao segue na agenda.
  if (WiFi.status() != WL_CONNECTED &&
      (ultimaTentativaWiFi == 0 || millis() - ultimaTentativaWiFi >= RECONEXAO_MS)) {

    Serial.println("Wi-Fi desconectado. Tentando reconectar em segundo plano...");
    logMotivo("sem conexao");

    iniciarWiFi(cfgSsid.c_str(), cfgSenha.c_str());
  }


  // --------------------------------------------------------
  // Controla intervalo de envio
  // --------------------------------------------------------

  unsigned long agora = millis();

  if (cicloImediato || cicloVencidoCore(agora, proximoCiclo)) {

    // Agenda fixa: o proximo ciclo conta do horario marcado deste, nao do
    // fim do envio (que roda na tarefa de envio).
    proximoCiclo = proximoCicloCore(agora, proximoCiclo, INTERVALO_ENVIO, cicloImediato);
    cicloImediato = false;

    Serial.print("CICLO: ");
    Serial.print(agora);
    Serial.println(" ms");


    // ======================================================
    // LEITURA DO SENSOR
    // ======================================================

    float temperatura, umidade;

    lerSensor(&temperatura, &umidade);


    Serial.println();
    Serial.println("----------------------------------------");


    // ======================================================
    // VALIDAÇÃO DO SENSOR
    // ======================================================

    if (isnan(temperatura) || isnan(umidade)) {

      Serial.println("ERRO: Falha na leitura do sensor!");

      // Leitura invalida nunca sai como valida: nada vai para a telemetria nem
      // para a fila. Tela: FALHA SENSOR; LEDs: os tres piscando juntos.
      indSensorFalhou = true;
      indTemperatura = NAN;
      indUmidade = NAN;
      desenharIndicadores();

      // Heartbeat (R7): a placa avisa que esta viva e que o sensor falhou, para
      // o painel nao confundir com placa sem rede. So com conexao: heartbeat
      // nao entra na fila offline. A fila de leituras validas de antes segue
      // sendo reenviada.
      if (conexaoDisponivel()) {

        // A tarefa de envio manda depois de esvaziar a fila.
        heartbeatPedidoEm = millis();
        heartbeatPendente = true;
        avisarEnvio();
      }

      else {

        Serial.println("Sem conexao. Heartbeat nao enviado (heartbeat nao vai para a fila).");
      }

      Serial.println("----------------------------------------");
      return;
    }


    // ======================================================
    // DADOS DO MICROCLIMA
    // ======================================================

    Serial.print("Temperatura: ");
    Serial.print(temperatura, 1);
    Serial.println(" C");

    Serial.print("Umidade: ");
    Serial.print(umidade, 1);
    Serial.println(" %");


    // ======================================================
    // CLASSIFICAÇÃO EDGE
    // ======================================================

    // Mesma regra da nuvem (contrato.py): sem limite inferior quando faixaMin e NAN.
    switch (classificarFaixa(temperatura, faixaMin, faixaMax, faixaMargem)) {

      case StatusTermico::NORMAL:
        statusNormal();
        break;

      case StatusTermico::ATENCAO:
        statusAtencao();
        break;

      default:
        statusCritico();
        break;
    }

    indSensorFalhou = false;
    indTemperatura = temperatura;
    indUmidade = umidade;
    desenharIndicadores();


    // ======================================================
    // RSSI WI-FI
    // ======================================================

    long rssi = WiFi.RSSI();

    Serial.print("RSSI Wi-Fi: ");
    Serial.print(rssi);
    Serial.println(" dBm");


    // ======================================================
    // PAYLOAD COM O HORARIO DA MEDICAO
    // ======================================================

    time_t medidoEm = relogioOk() ? time(nullptr) : 0;
    unsigned long msMedicao = millis();

    char payload[160];

    // RSSI >= 0 (simulador) vai como null; sem relogio, medidoEm e omitido.
    uint32_t seq = proximaSeq();

    montarPayloadCore(payload, sizeof(payload), cfgId.c_str(),
                      temperatura, umidade, rssi, medidoEm, seq);

    Serial.print("Payload JSON: ");
    Serial.println(payload);


    // ======================================================
    // FILA E ENVIO (store-and-forward)
    // ======================================================

    // A leitura vai para a fila na flash logo depois de ganhar o numero, com
    // ou sem rede: um reinicio daqui em diante nao a perde. A tarefa de envio
    // tira da fila quando a nuvem confirma. Nada aqui espera a rede.
    bool online = conexaoDisponivel();

    if (!online) {
      Serial.println("Sem conexao. Telemetria nao enviada agora.");
    }

    if (!guardarLeitura(payload, medidoEm, msMedicao, !online) && online) {
      pedirEnvioDireto(payload);
    }

#ifdef COM_MQTT
    if (online) {
      portENTER_CRITICAL(&mqttLeituraTrava);
      leituraMqtt = { true, temperatura, umidade, rssi, millis() };
      portEXIT_CRITICAL(&mqttLeituraTrava);
    }
#endif

    avisarEnvio();


    Serial.println("----------------------------------------");
  }
}
