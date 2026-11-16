#ifndef PAYLOAD_CORE_H
#define PAYLOAD_CORE_H

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <math.h>
#include <string>

// seq: numero de sequencia da leitura (1, 2, 3...); 0 = sem seq (campo omitido).
inline void montarPayloadCore(char *destino, size_t tamanho, const char *deviceId,
                              float temperatura, float umidade, long rssi, time_t medidoEm,
                              uint32_t seq = 0) {
    char rssiJson[16];
    if (rssi < 0) {
        snprintf(rssiJson, sizeof(rssiJson), "%ld", rssi);
    } else {
        snprintf(rssiJson, sizeof(rssiJson), "null");
    }

    char seqJson[24] = "";
    if (seq > 0) {
        snprintf(seqJson, sizeof(seqJson), ",\"seq\":%lu", (unsigned long)seq);
    }

    char medidoJson[32] = "";
    if (medidoEm > 0) {
        snprintf(medidoJson, sizeof(medidoJson), ",\"medidoEm\":%lld", (long long)medidoEm);
    }

    snprintf(destino, tamanho,
             "{\"deviceId\":\"%s\",\"temperatura\":%.1f,\"umidade\":%.1f,\"rssi\":%s%s%s}",
             deviceId ? deviceId : "", temperatura, umidade, rssiJson, seqJson, medidoJson);
}

inline float extrairNumeroJson(const std::string &json, const std::string &chave) {
    std::string alvo = "\"" + chave + "\":";
    size_t pos = json.find(alvo);
    if (pos == std::string::npos) return NAN;

    pos += alvo.length();
    while (pos < json.length() && (json[pos] == ' ' || json[pos] == '\t')) {
        pos++;
    }
    if (json.compare(pos, 4, "null") == 0) return NAN;

    try {
        return std::stof(json.substr(pos));
    } catch (...) {
        return NAN;
    }
}

enum class StatusTermico {
    NORMAL,
    ATENCAO,
    CRITICO
};

inline StatusTermico classificarFaixa(float temp, float faixaMin, float faixaMax, float margem) {
    if (isnan(temp)) return StatusTermico::CRITICO;
    
    bool dentroMin = isnan(faixaMin) || (temp >= faixaMin);
    bool dentroMax = (temp <= faixaMax);
    if (dentroMin && dentroMax) {
        return StatusTermico::NORMAL;
    }

    bool dentroMargemMin = isnan(faixaMin) || (temp >= (faixaMin - margem));
    bool dentroMargemMax = (temp <= (faixaMax + margem));
    if (dentroMargemMin && dentroMargemMax) {
        return StatusTermico::ATENCAO;
    }

    return StatusTermico::CRITICO;
}

#endif

