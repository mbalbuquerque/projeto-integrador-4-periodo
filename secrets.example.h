#pragma once

// Copie este arquivo para secrets.h e preencha com os valores reais.
// O secrets.h está no .gitignore e NUNCA deve ser commitado.

// Wi-Fi (no simulador Wokwi use a rede aberta "Wokwi-GUEST")
#define WIFI_SSID     "Wokwi-GUEST"
#define WIFI_PASSWORD ""

// Sensor: descomente na placa física com DHT11 (o padrão é DHT22, usado no Wokwi)
// #define DHT_TYPE DHT11

// Identidade do sensor: registre em painel > Sensores > Registrar sensor.
// A chave aparece uma vez só, na hora do registro.
#define DEVICE_ID  "coldtrack-01"
#define DEVICE_KEY "CHAVE_DO_SENSOR"

// Azure Function (endpoint de telemetria)
#define AZURE_FUNCTION_URL "https://func-coldtrack-7319.azurewebsites.net/api/telemetria"
