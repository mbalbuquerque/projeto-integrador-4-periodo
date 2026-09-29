#pragma once

// Copie este arquivo para secrets.h. O secrets.h está no .gitignore e NUNCA deve ser commitado.
//
// Na placa física, Wi-Fi, ID e chave são configurados pelo cabo USB:
// painel > Sensores > "Conectar sensor pelo cabo" (Chrome ou Edge no computador).
// O que ficar salvo na placa vale mais que este arquivo. Os valores abaixo só são
// usados enquanto a placa não tem configuração salva (é assim no simulador Wokwi).
// Pode apagar WIFI_*, DEVICE_ID e DEVICE_KEY: a placa espera a configuração pelo cabo.

// Wi-Fi (no simulador Wokwi use a rede aberta "Wokwi-GUEST")
#define WIFI_SSID     "Wokwi-GUEST"
#define WIFI_PASSWORD ""

// Sensor: descomente na placa física com DHT11 (o padrão é DHT22, usado no Wokwi)
// #define DHT_TYPE DHT11

// Identidade do sensor (Wokwi): registre em painel > Sensores > "Registrar sem cabo".
// A chave aparece uma vez só, na hora do registro.
#define DEVICE_ID  "coldtrack-01"
#define DEVICE_KEY "CHAVE_DO_SENSOR"

// Azure Function (endpoint de telemetria). Opcional: o firmware já usa este por padrão.
#define AZURE_FUNCTION_URL "https://func-coldtrack-7319.azurewebsites.net/api/telemetria"
