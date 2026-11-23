#ifndef PAYLOAD_CORE_H
#define PAYLOAD_CORE_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>
#include <string>

// seq: numero de sequencia da leitura (1, 2, 3...); 0 = sem seq (campo omitido).
// origem: "placa" (padrao) ou "simulador"; nulo/vazio = "placa".
inline void montarPayloadCore(char *destino, size_t tamanho, const char *deviceId,
                              float temperatura, float umidade, long rssi, time_t medidoEm,
                              uint32_t seq = 0, const char *origem = "placa") {
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
             "{\"deviceId\":\"%s\",\"temperatura\":%.1f,\"umidade\":%.1f,\"rssi\":%s%s%s,\"origem\":\"%s\"}",
             deviceId ? deviceId : "", temperatura, umidade, rssiJson, seqJson, medidoJson,
             (origem && origem[0]) ? origem : "placa");
}

// Heartbeat (POST /api/heartbeat): placa viva sem leitura valida para enviar.
// seq: ultima sequencia usada por leitura (0 = omitido); o heartbeat nao gasta numero.
inline void montarHeartbeatCore(char *destino, size_t tamanho, const char *deviceId,
                                const char *motivo, const char *fw, long rssi,
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

    snprintf(destino, tamanho,
             "{\"deviceId\":\"%s\",\"motivo\":\"%s\",\"fw\":\"%s\",\"rssi\":%s%s}",
             deviceId ? deviceId : "", motivo, fw, rssiJson, seqJson);
}

// URL do heartbeat a partir da URL da telemetria: troca o ultimo "/telemetria"
// por "/heartbeat". Sem "/telemetria" na URL, devolve vazio (nao envia).
inline std::string urlHeartbeatCore(const std::string &urlTelemetria) {
    const std::string rota = "/telemetria";
    size_t pos = urlTelemetria.rfind(rota);
    if (pos == std::string::npos) return "";
    return urlTelemetria.substr(0, pos) + "/heartbeat" + urlTelemetria.substr(pos + rota.size());
}

// Agenda fixa da medicao: o proximo ciclo e o anterior + intervalo, contado do
// inicio ao inicio, sem depender de quanto o envio demorou. Se a placa ficou
// parada mais de um intervalo inteiro (configuracao pelo cabo, por exemplo), a
// agenda recomeca de agora, sem rajada de leituras para compensar.
// `previsto` e o horario em que o ciclo que comeca agora estava marcado.
// Conta com a volta do millis() (unsigned).
inline unsigned long proximoCicloCore(unsigned long agora, unsigned long previsto,
                                      unsigned long intervalo, bool recomecar) {
    if (recomecar || agora - previsto >= intervalo) {
        return agora + intervalo;
    }
    return previsto + intervalo;
}

// Ja passou do horario marcado? (com a volta do millis())
inline bool cicloVencidoCore(unsigned long agora, unsigned long previsto) {
    return (long)(agora - previsto) >= 0;
}

// Linha da fila guardada sem relogio: {...,"ms":<millis da medicao>}.
// Devolve true e o millis se a linha tem o campo; `semMs` recebe a linha sem ele.
inline bool linhaComMsCore(const std::string &linha, unsigned long *ms, std::string *semMs) {
    const std::string campo = ",\"ms\":";
    size_t pos = linha.find(campo);
    if (pos == std::string::npos) return false;
    size_t inicio = pos + campo.size();
    size_t fim = inicio;
    while (fim < linha.size() && linha[fim] >= '0' && linha[fim] <= '9') fim++;
    if (fim == inicio) return false;
    if (ms) *ms = strtoul(linha.substr(inicio, fim - inicio).c_str(), nullptr, 10);
    if (semMs) *semMs = linha.substr(0, pos) + linha.substr(fim);
    return true;
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

// ---------------------------------------------------------------------------
// Filtro de mediana (janela deslizante) sobre as leituras validas do DHT.
// A mediana descarta um pico isolado (leitura esticada por interrupcao, ruido do fio)
// sem atrasar a tendencia como a media faria. Leitura invalida (NAN) NUNCA entra na
// janela: o chamador valida antes e a funcao ignora NAN por seguranca.
// FILTRO_JANELA pode ser trocada no secrets.h (3 a 9; fora disso vale o padrao 5).
// FILTRO_JANELA 1 desliga o filtro (devolve a propria leitura).
// ---------------------------------------------------------------------------
#ifndef FILTRO_JANELA
#define FILTRO_JANELA 5
#endif
#define FILTRO_JANELA_MAX 9

struct FiltroMediana {
    float valores[FILTRO_JANELA_MAX];
    int quantidade;  // quantas leituras validas ha na janela (ate janela())
    int proximo;     // posicao circular da proxima gravacao
};

inline int filtroJanela() {
    if (FILTRO_JANELA == 1) return 1;
    if (FILTRO_JANELA < 3 || FILTRO_JANELA > FILTRO_JANELA_MAX) return 5;
    return FILTRO_JANELA;
}

inline void filtroReiniciar(FiltroMediana *f) {
    f->quantidade = 0;
    f->proximo = 0;
}

// Acrescenta `valor` e devolve a mediana da janela. Com menos leituras que a janela,
// usa as que existem (par: media dos dois centrais). NAN: nao entra e devolve NAN.
inline float filtroMediana(FiltroMediana *f, float valor) {
    if (isnan(valor)) return NAN;
    int janela = filtroJanela();
    if (janela == 1) return valor;
    if (f->quantidade > janela || f->quantidade < 0 || f->proximo < 0 || f->proximo >= janela) {
        filtroReiniciar(f);
    }
    f->valores[f->proximo] = valor;
    f->proximo = (f->proximo + 1) % janela;
    if (f->quantidade < janela) f->quantidade++;

    float ord[FILTRO_JANELA_MAX];
    int n = f->quantidade;
    for (int i = 0; i < n; i++) ord[i] = f->valores[i];
    for (int i = 1; i < n; i++) {  // insercao: n <= 9
        float v = ord[i];
        int j = i - 1;
        while (j >= 0 && ord[j] > v) { ord[j + 1] = ord[j]; j--; }
        ord[j + 1] = v;
    }
    if (n % 2 == 1) return ord[n / 2];
    return (ord[n / 2 - 1] + ord[n / 2]) / 2.0f;
}
#endif
