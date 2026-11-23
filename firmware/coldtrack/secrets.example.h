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

// Origem da leitura no banco: este exemplo e o build do simulador Wokwi, entao marca
// "simulador". Na placa fisica APAGUE esta linha (sem ela o padrao e "placa").
#define ORIGEM_SIMULADOR

// Sensor: descomente na placa física com DHT11 (o padrão é DHT22, usado no Wokwi)
// #define DHT_TYPE DHT11

// LED da placa física (opcional; confira qual a placa tem antes de ligar).
// LED simples aceso em nível baixo no GPIO 8:
// #define LED_PLACA 8
// #define LED_PLACA_ATIVO_BAIXO
// LED RGB WS2812 no GPIO 2 (mostra a cor da faixa):
// #define LED_PLACA 2
// #define LED_PLACA_RGB

// Identidade do sensor (Wokwi): registre em painel > Sensores > "Registrar sem cabo".
// A chave aparece uma vez só, na hora do registro.
#define DEVICE_ID  "coldtrack-01"
#define DEVICE_KEY "CHAVE_DO_SENSOR"

// Azure Function (endpoint de telemetria). Opcional: o firmware já usa este por padrão.
#define AZURE_FUNCTION_URL "https://func-coldtrack-7319.azurewebsites.net/api/telemetria"

// Filtro de mediana sobre as leituras validas do DHT (3 a 9 leituras; padrao 5; 1 desliga).
// Mediana de 5 leituras a cada 20 s descarta um pico isolado e atrasa a tendencia em ~40 s.
// #define FILTRO_JANELA 5
