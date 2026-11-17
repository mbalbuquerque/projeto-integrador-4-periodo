#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <time.h>
#include "driver/gpio.h"
#include <Preferences.h>
#include <esp_task_wdt.h>
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
//   MEDIDA;<https|mqtt|mqtt-conexao>;<ms>;<bytes enviados>;<bytes recebidos>;<ok 1/0>

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
 ==========================================================
*/

// ================= CONFIGURACAO DO SENSOR =================
//
// Wi-Fi, ID e chave chegam pelo cabo USB: painel > Sensores > "Conectar
// sensor pelo cabo" (Web Serial) e ficam guardados na flash.
// Sem nada salvo, vale o que estiver no secrets.h (e assim no Wokwi).
// Sem nenhum dos dois, o sensor so mede e espera o cabo.

#define FW_VERSAO "2026.11.16.3"

#ifndef AZURE_FUNCTION_URL
#define AZURE_FUNCTION_URL "https://func-coldtrack-7319.azurewebsites.net/api/telemetria"
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


// Tempo maximo de espera da requisicao HTTPS, em ms.
#define HTTP_TIMEOUT_MS 5000

// ================= STORE-AND-FORWARD =================
//
// Sem conexao (estrada sem sinal), a leitura fica guardada na flash
// e e reenviada quando a conexao volta, com o horario da medicao.

#define FILA_ARQUIVO      "/fila.jsonl"
#define FILA_MAX          500   // ~2h45 de leituras a cada 20 s
#define REENVIO_POR_CICLO 10    // limita o tempo gasto reenviando por ciclo

// Teste: finge conexao caida nos primeiros N segundos (0 = desligado).
#ifndef SIMULAR_QUEDA_S
#define SIMULAR_QUEDA_S 0
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
    delay(1000);  // o sensor precisa de ~1 s depois de ligado
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
      delay(DHT_TYPE == DHT11 ? 1100 : 2100);
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
// envio retoma sozinho depois do reinicio. Os trechos longos (Wi-Fi, reenvio
// da fila) alimentam o watchdog no meio; o pior caso legitimo entre duas
// alimentacoes e uma requisicao HTTPS (conexao + TLS + 5 s de resposta).

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

const unsigned long INTERVALO_ENVIO = 20000;

unsigned long ultimoEnvio = 0;


// ==========================================================
// CONTROLE DOS LEDs
// ==========================================================

#ifdef TELA_OLED

// 72x40 pixels: temperatura grande em cima, umidade e status embaixo.
void mostrarNaTela(float temperatura, float umidade, const char *status) {

  char linha[16];

  tela.clearBuffer();

  tela.setFont(u8g2_font_7x14B_tf);
  if (isnan(temperatura)) {
    tela.drawStr(0, 13, "--.- C");
  } else {
    snprintf(linha, sizeof(linha), "%.1f C", temperatura);
    tela.drawStr(0, 13, linha);
  }

  tela.setFont(u8g2_font_6x10_tf);
  if (!isnan(umidade)) {
    snprintf(linha, sizeof(linha), "U %.0f%%", umidade);
    tela.drawStr(0, 26, linha);
  }
  tela.drawStr(0, 39, status);

  tela.sendBuffer();
}

#endif


void desligarLeds() {

#ifndef TELA_OLED
  digitalWrite(LED_VERDE, LOW);
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERMELHO, LOW);
#endif
}


void statusNormal() {

  desligarLeds();

#ifndef TELA_OLED
  digitalWrite(LED_VERDE, HIGH);
#endif

  Serial.println("STATUS DA CARGA: NORMAL");
}


void statusAtencao() {

  desligarLeds();

#ifndef TELA_OLED
  digitalWrite(LED_AMARELO, HIGH);
#endif

  Serial.println("STATUS DA CARGA: ATENCAO");
}


void statusCritico() {

  desligarLeds();

#ifndef TELA_OLED
  digitalWrite(LED_VERMELHO, HIGH);
#endif

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

  while (WiFi.status() != WL_CONNECTED && tentativas < 20) {

    delay(500);
    alimentarWatchdog();

    Serial.print(".");

    tentativas++;

    // Chegou configuracao pelo cabo: para de esperar e deixa o loop tratar.
    if (lerSerial()) {
      break;
    }
  }

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

  // Grava so quando muda: poupa a flash.
  preferencias.begin("coldtrack", false);
  preferencias.putFloat("min", faixaMin);
  preferencias.putFloat("max", faixaMax);
  preferencias.putFloat("margem", faixaMargem);
  preferencias.end();

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

  ClienteContado clienteSeguro;
  clienteSeguro.setCACert(AZURE_ROOT_CA);

  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);

  // Tempo e bytes do envio inteiro: conexao TCP + TLS + requisicao + resposta.
  unsigned long inicio = millis();

  if (!http.begin(clienteSeguro, AZURE_FUNCTION_URL)) {

    Serial.println("Azure: falha ao iniciar conexao HTTPS.");
    registrarMedida("https", millis() - inicio, 0, 0, false);
    return -1;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("x-device-key", cfgChave);

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
#define MQTT_KEEPALIVE  120   // s; maior que o pior ciclo (Azure + 10 reenvios)
#define MQTT_TIMEOUT    5     // s

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

void sincronizarRelogio() {

  configTime(0, 0, "pool.ntp.org", "time.google.com");
}


bool relogioOk() {

  if (SIMULAR_SEM_RELOGIO_S > 0 && millis() < SIMULAR_SEM_RELOGIO_S * 1000UL) {
    return false;
  }

  return time(nullptr) >= EPOCH_VALIDO;
}


// ==========================================================
// CONEXAO
// ==========================================================

bool conexaoDisponivel() {

  if (SIMULAR_QUEDA_S > 0 && millis() < SIMULAR_QUEDA_S * 1000UL) {
    return false;
  }

  return WiFi.status() == WL_CONNECTED;
}


// ==========================================================
// FILA EM FLASH (STORE-AND-FORWARD)
// ==========================================================

int contarFila() {

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


// Reescreve a fila pulando as `pular` primeiras linhas.
void descartarInicioDaFila(int pular) {

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


// Linhas guardadas sem relogio levam "ms" (millis da medicao) no lugar do medidoEm.
bool filaTemMs = false;


bool linhaTemMs(const String &linha) {

  return linha.indexOf("\"ms\":") >= 0;
}


// Reescreve a fila tratando as linhas com "ms":
//   converter = true: troca "ms" pelo medidoEm (agora - tempo desde a medicao);
//   converter = false: descarta (vieram de antes de um reinicio, o millis zerou).
void reescreverFilaMs(bool converter) {

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


void enfileirar(const char *payload) {

  File arquivo = LittleFS.open(FILA_ARQUIVO, "a");

  if (!arquivo) {

    Serial.println("FILA: erro ao abrir a flash. Leitura perdida.");
    return;
  }

  arquivo.println(payload);
  arquivo.close();

  filaTamanho++;

  if (filaTamanho > FILA_MAX) {

    Serial.println("FILA: cheia, descartando a leitura mais antiga.");
    descartarInicioDaFila(filaTamanho - FILA_MAX);
  }

  Serial.print("FILA: leitura guardada offline (");
  Serial.print(filaTamanho);
  Serial.println(" na fila).");
}


// Guarda a leitura para reenvio. Sem relogio, guarda o millis da medicao.
void guardarOffline(const char *payload, time_t medidoEm, unsigned long msMedicao) {

  if (medidoEm > 0) {
    enfileirar(payload);
    return;
  }

  String linha = payload;
  int fim = linha.lastIndexOf('}');

  linha = linha.substring(0, fim) + ",\"ms\":" + String(msMedicao) + "}";

  Serial.println("FILA: sem relogio; guardando com o tempo desde que a placa ligou.");
  enfileirar(linha.c_str());
  filaTemMs = true;
}


// Envia as leituras guardadas, da mais antiga para a mais nova.
// Para na primeira falha temporaria para manter a ordem.
void reenviarFila() {

  if (filaTamanho == 0) {
    return;
  }

  if (filaTemMs && relogioOk()) {
    reescreverFilaMs(true);
  }

  if (filaTamanho == 0) {
    return;
  }

  Serial.print("FILA: reenviando (");
  Serial.print(filaTamanho);
  Serial.println(" pendentes)...");

  File arquivo = LittleFS.open(FILA_ARQUIVO, "r");

  if (!arquivo) {

    filaTamanho = 0;
    return;
  }

  int processadas = 0;

  while (arquivo.available() && processadas < REENVIO_POR_CICLO) {

    String linha = arquivo.readStringUntil('\n');
    linha.trim();

    if (linha.length() == 0) {
      continue;
    }

    // Leitura sem horario so sai depois do relogio (a API nao aceita "ms").
    if (linhaTemMs(linha)) {
      Serial.println("FILA: aguardando o relogio para reenviar leituras sem horario.");
      break;
    }

    alimentarWatchdog();

    Serial.print("FILA: reenviando ");
    Serial.println(linha);

    int status = postarAzure(linha.c_str());

    if (falhaTemporaria(status)) {
      break;
    }

    processadas++;
  }

  arquivo.close();

  if (processadas > 0) {

    descartarInicioDaFila(processadas);

    Serial.print("FILA: ");
    Serial.print(processadas);
    Serial.print(" reenviadas, ");
    Serial.print(filaTamanho);
    Serial.println(" restantes.");
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
      delay(50);
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

    delay(250);
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

  LittleFS.remove(FILA_ARQUIVO);
  filaTamanho = 0;
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
    return;
  }

  if (tipo == "wifi" && !temIdentidade()) {

    responder("{\"ok\":false,\"erro\":\"sem_identidade\"}");
    return;
  }

  if (tipo == "config" && (id.length() < 3 || id.length() > 40 || chave.length() < 16)) {

    responder("{\"ok\":false,\"erro\":\"identidade_invalida\"}");
    return;
  }

  Serial.print("CONFIG: testando a rede ");
  Serial.println(ssid);

  String erro = testarWiFi(ssid, senha);

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
    cfgId = id;
    cfgChave = chave;
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

  // Proxima leitura sai ja, para o painel mostrar "online" logo.
  ultimoEnvio = 0;
}


// ==========================================================
// SETUP
// ==========================================================

void setup() {

  // Comando de configuracao passa de 200 bytes; o buffer padrao e pequeno.
  Serial.setRxBufferSize(1024);
  Serial.begin(115200);

  iniciarWatchdog();

  delay(1000);

#ifdef TELA_OLED
  Wire.begin(TELA_SDA, TELA_SCL);
  tela.begin();
  tela.setContrast(255);
  mostrarNaTela(NAN, NAN, "INICIANDO");
#else
  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_AMARELO, OUTPUT);
  pinMode(LED_VERMELHO, OUTPUT);

  desligarLeds();
#endif

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

  Serial.println();
  Serial.println("Sistema iniciado.");

  // Linha de prontidao: o painel espera por ela (ou por um "info" respondido)
  // antes de mandar comandos, porque abrir a porta pode reiniciar a placa.
  responder(String("{\"pronto\":true,\"fw\":") + emJson(FW_VERSAO) + "}");
}


// ==========================================================
// LOOP
// ==========================================================

void loop() {

  alimentarWatchdog();

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

#ifdef COM_MQTT
  // Mantem a conexao viva (PINGREQ) e processa o que o broker mandar.
  mqtt.loop();
#endif


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
      float t, u;
      lerSensor(&t, &u);
      mostrarNaTela(t, u, "CONFIGURAR");
    }
#else
    digitalWrite(LED_AMARELO, (millis() / 500) % 2);
#endif

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

  // Uma tentativa nova a cada RECONEXAO_MS: no meio delas o driver segue
  // tentando sozinho, e a leitura e a fila continuam andando.
  if (WiFi.status() != WL_CONNECTED &&
      (ultimaTentativaWiFi == 0 || millis() - ultimaTentativaWiFi >= RECONEXAO_MS)) {

    Serial.println("Wi-Fi desconectado.");
    Serial.println("Tentando reconectar...");

    conectarWiFi();
  }


  // --------------------------------------------------------
  // Controla intervalo de envio
  // --------------------------------------------------------

  if (millis() - ultimoEnvio >= INTERVALO_ENVIO ||
      ultimoEnvio == 0) {

    ultimoEnvio = millis();


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

      desligarLeds();

#ifdef TELA_OLED
      mostrarNaTela(NAN, NAN, "ERRO SENSOR");
#else
      digitalWrite(LED_VERMELHO, HIGH);
      delay(300);
      digitalWrite(LED_VERMELHO, LOW);
#endif

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
    const char *statusTela;

    switch (classificarFaixa(temperatura, faixaMin, faixaMax, faixaMargem)) {

      case StatusTermico::NORMAL:
        statusNormal();
        statusTela = "NORMAL";
        break;

      case StatusTermico::ATENCAO:
        statusAtencao();
        statusTela = "ATENCAO";
        break;

      default:
        statusCritico();
        statusTela = "CRITICO";
        break;
    }

#ifdef TELA_OLED
    mostrarNaTela(temperatura, umidade, statusTela);
#else
    (void)statusTela;
#endif


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
    // ENVIO (Azure com store-and-forward)
    // ======================================================

    if (conexaoDisponivel()) {

      Serial.println();

      // Primeiro o que ficou guardado, para manter a ordem no banco.
      reenviarFila();

      Serial.println("Enviando telemetria ao Azure...");

      alimentarWatchdog();

      int status = postarAzure(payload);

#ifdef COM_MQTT
      alimentarWatchdog();
      publicarMqtt(temperatura, umidade, rssi);
#endif

      if (falhaTemporaria(status)) {

        guardarOffline(payload, medidoEm, msMedicao);
      }

    }

    else {

      Serial.println("Sem conexao. Telemetria nao enviada agora.");

      guardarOffline(payload, medidoEm, msMedicao);
    }


    Serial.println("----------------------------------------");
  }
}
