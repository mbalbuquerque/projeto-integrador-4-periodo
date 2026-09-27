#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <time.h>
#include <DHT.h>
#include <Preferences.h>
#include "secrets.h"
#include "azure_ca.h"

/*
 ==========================================================
 COLDTRACK EDGE
 Monitoramento IoT de Transporte Refrigerado

 ESP32-C3 + DHT + LEDs + Wi-Fi + Azure

 Envio: POST JSON via HTTPS (TLS validado) na Azure Function
 {"deviceId":"coldtrack-01","temperatura":12.4,"umidade":81.0,"rssi":-58,"medidoEm":1790000000}
 ==========================================================
*/

// DEVICE_ID e DEVICE_KEY vem do secrets.h: cada sensor tem o proprio ID
// e a propria chave, gerados ao registrar o sensor no painel.
#if !defined(DEVICE_ID) || !defined(DEVICE_KEY)
#error "Defina DEVICE_ID e DEVICE_KEY no secrets.h (painel > Sensores > Registrar sensor)"
#endif

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

// Epoch minimo aceito como relogio sincronizado (nov/2023).
#define EPOCH_VALIDO 1700000000

int filaTamanho = 0;

// ================= PINAGEM =================

#define DHT_PIN 4
// DHT22 na simulacao Wokwi. Na placa fisica com DHT11, defina
// DHT_TYPE DHT11 no secrets.h (ele e incluido antes deste ponto).
#ifndef DHT_TYPE
#define DHT_TYPE DHT22
#endif

#define LED_VERDE    5
#define LED_AMARELO  6
#define LED_VERMELHO 7

DHT dht(DHT_PIN, DHT_TYPE);


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

void desligarLeds() {

  digitalWrite(LED_VERDE, LOW);
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERMELHO, LOW);
}


void statusNormal() {

  desligarLeds();

  digitalWrite(LED_VERDE, HIGH);

  Serial.println("STATUS DA CARGA: NORMAL");
}


void statusAtencao() {

  desligarLeds();

  digitalWrite(LED_AMARELO, HIGH);

  Serial.println("STATUS DA CARGA: ATENCAO");
}


void statusCritico() {

  desligarLeds();

  digitalWrite(LED_VERMELHO, HIGH);

  Serial.println("STATUS DA CARGA: CRITICO");
}


// ==========================================================
// CONEXÃO WI-FI
// ==========================================================

void conectarWiFi() {

  Serial.println();
  Serial.print("Conectando ao Wi-Fi");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tentativas = 0;

  while (WiFi.status() != WL_CONNECTED && tentativas < 20) {

    delay(500);

    Serial.print(".");

    tentativas++;
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
    DEVICE_ID, temperatura, umidade, rssiJson, medidoJson);
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

  WiFiClientSecure clienteSeguro;
  clienteSeguro.setCACert(AZURE_ROOT_CA);

  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);

  if (!http.begin(clienteSeguro, AZURE_FUNCTION_URL)) {

    Serial.println("Azure: falha ao iniciar conexao HTTPS.");
    return -1;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("x-device-key", DEVICE_KEY);

  int status = http.POST(payload);

  if (status == 201) {

    String resposta = http.getString();

    Serial.print("Azure: gravado. Resposta: ");
    Serial.println(resposta);

    atualizarFaixa(resposta);

  }

  else {

    Serial.print("Azure: erro HTTP ");
    Serial.print(status);
    Serial.print(" ");
    Serial.println(status > 0 ? http.getString() : http.errorToString(status));
  }

  http.end();

  return status;
}


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


// Envia as leituras guardadas, da mais antiga para a mais nova.
// Para na primeira falha temporaria para manter a ordem.
void reenviarFila() {

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
// SETUP
// ==========================================================

void setup() {

  Serial.begin(115200);

  delay(1000);

  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_AMARELO, OUTPUT);
  pinMode(LED_VERMELHO, OUTPUT);

  desligarLeds();

  dht.begin();

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

  carregarFaixa();

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

    float temperatura = dht.readTemperature();
    float umidade = dht.readHumidity();


    Serial.println();
    Serial.println("----------------------------------------");


    // ======================================================
    // VALIDAÇÃO DO SENSOR
    // ======================================================

    if (isnan(temperatura) || isnan(umidade)) {

      Serial.println("ERRO: Falha na leitura do sensor!");

      desligarLeds();

      digitalWrite(LED_VERMELHO, HIGH);
      delay(300);
      digitalWrite(LED_VERMELHO, LOW);

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

    if (temperatura >= minimo && temperatura <= faixaMax) {

      statusNormal();

    }

    else if (temperatura >= minimo - faixaMargem && temperatura <= faixaMax + faixaMargem) {

      statusAtencao();

    }

    else {

      statusCritico();
    }


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

      if (falhaTemporaria(status)) {

        if (medidoEm > 0) {
          enfileirar(payload);
        } else {
          Serial.println("FILA: sem relogio sincronizado, leitura nao guardada.");
        }
      }

    }

    else {

      Serial.println("Sem conexao. Telemetria nao enviada agora.");

      if (medidoEm > 0) {
        enfileirar(payload);
      } else {
        Serial.println("FILA: sem relogio sincronizado, leitura nao guardada.");
      }
    }


    Serial.println("----------------------------------------");
  }
}
