#include <WiFi.h>
#include <ThingSpeak.h>
#include <DHT.h>
#include "secrets.h"

/*
 ==========================================================
 COLDTRACK EDGE
 Monitoramento IoT de Transporte Refrigerado

 ESP32-C3 + DHT + LEDs + Wi-Fi + ThingSpeak

 Field 1 -> Temperatura
 Field 2 -> Umidade Relativa
 Field 3 -> RSSI Wi-Fi
 ==========================================================
*/

// ================= PINAGEM =================

#define DHT_PIN 4
#define DHT_TYPE DHT22   // Simulação Wokwi

#define LED_VERDE    5
#define LED_AMARELO  6
#define LED_VERMELHO 7

DHT dht(DHT_PIN, DHT_TYPE);

WiFiClient client;


// ================= LIMITES =================
//
// Limites demonstrativos do protótipo.
// Posteriormente serão adequados ao tipo de carga.
//

const float TEMP_NORMAL_MAX = 15.0;
const float TEMP_ATENCAO_MAX = 20.0;


// ================= TEMPORIZAÇÃO =================

// ThingSpeak exige intervalo mínimo entre atualizações.
// Utilizamos 20 segundos por segurança.

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

  conectarWiFi();

  ThingSpeak.begin(client);

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

    if (temperatura <= TEMP_NORMAL_MAX) {

      statusNormal();

    }

    else if (temperatura <= TEMP_ATENCAO_MAX) {

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
    // ENVIO PARA THINGSPEAK
    // ======================================================

    if (WiFi.status() == WL_CONNECTED) {

      ThingSpeak.setField(1, temperatura);

      ThingSpeak.setField(2, umidade);

      ThingSpeak.setField(3, (int)rssi);


      Serial.println();
      Serial.println("Enviando telemetria ao ThingSpeak...");


      int resultado = ThingSpeak.writeFields(
        THINGSPEAK_CHANNEL_ID,
        THINGSPEAK_WRITE_API_KEY
      );


      if (resultado == 200) {

        Serial.println("ThingSpeak: envio realizado com sucesso!");

      }

      else {

        Serial.print("ThingSpeak: erro HTTP ");
        Serial.println(resultado);
      }

    }

    else {

      Serial.println("Sem Wi-Fi. Telemetria não enviada.");
    }


    Serial.println("----------------------------------------");
  }
}
