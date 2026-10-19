#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <time.h>
#include "driver/gpio.h"
#include <Preferences.h>
#include "secrets.h"
#include "azure_ca.h"

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

#define FW_VERSAO "2026.09.28"

#ifndef AZURE_FUNCTION_URL
#define AZURE_FUNCTION_URL "https://func-coldtrack-7319.azurewebsites.net/api/telemetria"
#endif

// Tempo para testar uma rede nova recebida pelo cabo, em ms.
#define TESTE_WIFI_MS 15000

String cfgSsid;
String cfgSenha;
String cfgId;
String cfgChave;

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
  gpio_set_level((gpio_num_t)DHT_PIN, 1);

  // Resposta: sobe, cai ~80 us, sobe ~80 us.
  if (esperarNivel(1, 200) < 0 || esperarNivel(0, 200) < 0 || esperarNivel(1, 200) < 0) {
    return false;
  }

  // 40 bits: ~50 us em baixo + alto de ~27 us (0) ou ~70 us (1).
  uint8_t d[5] = {0, 0, 0, 0, 0};

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


// ================= TEMPORIZAÇÃO =================

// Uma leitura a cada 20 segundos: detecta desvio rapido sem
// gastar dado a toa quando a conexao for celular.

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
void ajustarRadio() {
#ifdef TELA_OLED
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
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

  WiFi.begin(cfgSsid.c_str(), cfgSenha.c_str());
  ajustarRadio();

  int tentativas = 0;

  while (WiFi.status() != WL_CONNECTED && tentativas < 20) {

    delay(500);

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
    Serial.println("Falha na conexão Wi-Fi.");
  }
}


// ==========================================================
// ENVIO PARA AZURE (JSON via HTTPS)
// ==========================================================

void montarPayload(char *destino, size_t tamanho,
                   float temperatura, float umidade, long rssi, time_t medidoEm) {

  // RSSI de Wi-Fi e sempre negativo. Valor >= 0 (ex.: simulador) vai como null,
  // em vez de mandar um numero falso para o banco.
  char rssiJson[12];

  if (rssi < 0) {
    snprintf(rssiJson, sizeof(rssiJson), "%ld", rssi);
  } else {
    snprintf(rssiJson, sizeof(rssiJson), "null");
  }

  // Sem relogio sincronizado (medidoEm = 0) o campo e omitido
  // e a nuvem usa o horario de recebimento.
  char medidoJson[24] = "";

  if (medidoEm > 0) {
    snprintf(medidoJson, sizeof(medidoJson), ",\"medidoEm\":%lld", (long long)medidoEm);
  }

  snprintf(destino, tamanho,
    "{\"deviceId\":\"%s\",\"temperatura\":%.1f,\"umidade\":%.1f,\"rssi\":%s%s}",
    cfgId.c_str(), temperatura, umidade, rssiJson, medidoJson);
}


// ==========================================================
// FAIXA DA CARGA (vem da nuvem, fica na flash)
// ==========================================================

// Le o numero depois de "chave": no JSON. null ou ausente = NAN.
float numeroDoJson(const String &json, const char *chave) {

  String alvo = String("\"") + chave + "\":";
  int inicio = json.indexOf(alvo);

  if (inicio < 0) {
    return NAN;
  }

  inicio += alvo.length();

  // A nuvem responde com espaco depois dos dois-pontos ("min": null).
  while (inicio < (int)json.length() && json[inicio] == ' ') {
    inicio++;
  }

  if (json.startsWith("null", inicio)) {
    return NAN;
  }

  return json.substring(inicio).toFloat();
}


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

  String trecho = resposta.substring(pos);

  float novoMin = numeroDoJson(trecho, "min");
  float novoMax = numeroDoJson(trecho, "max");
  float novaMargem = numeroDoJson(trecho, "margem");

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
//
// A placa testa a rede antes de gravar e responde
//   CT>{"ok":true,"wifi":"conectado","rssi":-55}
//   CT>{"ok":false,"erro":"senha|rede_nao_encontrada|tempo|..."}
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


// Motivo da ultima queda do Wi-Fi (vem do evento do driver; 0 = nenhum).
volatile uint8_t motivoQueda = 0;

void aoCairWiFi(WiFiEvent_t evento, WiFiEventInfo_t info) {

  motivoQueda = info.wifi_sta_disconnected.reason;
}


String traduzirMotivo(uint8_t motivo) {

  switch (motivo) {

    case WIFI_REASON_NO_AP_FOUND:
    case WIFI_REASON_NO_AP_FOUND_W_COMPATIBLE_SECURITY:
    case WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD:
    case WIFI_REASON_NO_AP_FOUND_IN_RSSI_THRESHOLD:
      return "rede_nao_encontrada";

    case WIFI_REASON_AUTH_FAIL:
    case WIFI_REASON_AUTH_EXPIRE:
    case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_MIC_FAILURE:
      return "senha";
  }

  return "";
}


// Tenta a rede; devolve "" se conectou ou o motivo da falha.
String testarWiFi(const String &ssid, const String &senha) {

  WiFi.disconnect();
  delay(200);

  motivoQueda = 0;
  WiFi.begin(ssid.c_str(), senha.c_str());
  ajustarRadio();

  unsigned long inicio = millis();
  wl_status_t status = WiFi.status();

  while (millis() - inicio < TESTE_WIFI_MS) {

    status = WiFi.status();

    if (status == WL_CONNECTED || status == WL_CONNECT_FAILED ||
        status == WL_NO_SSID_AVAIL) {
      break;
    }

    // O driver ja disse por que caiu: nao precisa esperar o tempo todo.
    if (traduzirMotivo(motivoQueda).length() > 0 && millis() - inicio > 3000) {
      break;
    }

    delay(250);
  }

  if (status == WL_CONNECTED) {
    return "";
  }

  if (status == WL_NO_SSID_AVAIL) {
    return "rede_nao_encontrada";
  }

  if (status == WL_CONNECT_FAILED) {
    return "senha";
  }

  String motivo = traduzirMotivo(motivoQueda);

  return motivo.length() > 0 ? motivo : "tempo";
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
    Serial.println(". Nada foi gravado; voltando para a rede anterior.");

    responder("{\"ok\":false,\"erro\":\"" + erro + "\",\"motivo\":" + String(motivoQueda) + "}");

    WiFi.disconnect();
    if (cfgSsid.length() > 0) {
      WiFi.begin(cfgSsid.c_str(), cfgSenha.c_str());
      ajustarRadio();
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

  responder(String("{\"ok\":true,\"wifi\":\"conectado\",\"rssi\":") + WiFi.RSSI() +
            ",\"id\":" + emJson(cfgId) + "}");

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

  carregarConfig();

  // Modo estacao antes de tudo: o MAC (ID sugerido) so aparece com o radio ligado.
  WiFi.mode(WIFI_STA);
  WiFi.onEvent(aoCairWiFi, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);

  Serial.print("SENSOR: ");
  Serial.print(temIdentidade() ? cfgId : String("sem identidade (chip ") + idDoChip() + ")");
  Serial.print(" | firmware ");
  Serial.println(FW_VERSAO);

  Serial.print("FILA: ");
  Serial.print(filaTamanho);
  Serial.println(" leituras pendentes na flash.");

  conectarWiFi();

  sincronizarRelogio();

  Serial.println();
  Serial.println("Sistema iniciado.");
}


// ==========================================================
// LOOP
// ==========================================================

void loop() {

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

  if (WiFi.status() != WL_CONNECTED) {

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
    float minimo = isnan(faixaMin) ? -1000.0 : faixaMin;

    const char *statusTela;

    if (temperatura >= minimo && temperatura <= faixaMax) {

      statusNormal();
      statusTela = "NORMAL";

    }

    else if (temperatura >= minimo - faixaMargem && temperatura <= faixaMax + faixaMargem) {

      statusAtencao();
      statusTela = "ATENCAO";

    }

    else {

      statusCritico();
      statusTela = "CRITICO";
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

    montarPayload(payload, sizeof(payload),
                  temperatura, umidade, rssi, medidoEm);

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

      int status = postarAzure(payload);

#ifdef COM_MQTT
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
