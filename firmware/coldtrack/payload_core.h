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
// temperaturaBruta/umidadeBruta: leitura do sensor ANTES do filtro de mediana, para
// auditoria (temperatura/umidade levam o valor filtrado). NAN = campo omitido.
// O payload completo (deviceId de 40 e todos os campos) tem ~215 bytes.
#define PAYLOAD_TAMANHO 256
inline void montarPayloadCore(char *destino, size_t tamanho, const char *deviceId,
                              float temperatura, float umidade, long rssi, time_t medidoEm,
                              uint32_t seq = 0, const char *origem = "placa",
                              float temperaturaBruta = NAN, float umidadeBruta = NAN) {
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

    char brutaJson[64] = "";
    int usado = 0;
    if (!isnan(temperaturaBruta)) {
        usado = snprintf(brutaJson, sizeof(brutaJson), ",\"temperaturaBruta\":%.1f",
                         temperaturaBruta);
    }
    if (!isnan(umidadeBruta) && usado >= 0 && usado < (int)sizeof(brutaJson)) {
        snprintf(brutaJson + usado, sizeof(brutaJson) - usado, ",\"umidadeBruta\":%.1f",
                 umidadeBruta);
    }

    snprintf(destino, tamanho,
             "{\"deviceId\":\"%s\",\"temperatura\":%.1f,\"umidade\":%.1f%s,\"rssi\":%s%s%s,\"origem\":\"%s\"}",
             deviceId ? deviceId : "", temperatura, umidade, brutaJson, rssiJson, seqJson,
             medidoJson, (origem && origem[0]) ? origem : "placa");
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
// Janela valida: 1 (desliga o filtro) ou 3 a 9. FILTRO_JANELA (secrets.h) e so o
// padrao de fabrica; o valor em uso vem da flash (comando "parametros" pelo cabo).
// ---------------------------------------------------------------------------
#ifndef FILTRO_JANELA
#define FILTRO_JANELA 5
#endif
#define FILTRO_JANELA_MAX 9

struct FiltroMediana {
    float valores[FILTRO_JANELA_MAX];
    int quantidade;  // quantas leituras validas ha na janela (ate a janela)
    int proximo;     // posicao circular da proxima gravacao
    int janela;      // tamanho da janela em uso (invalido = padrao de fabrica)
};

inline bool janelaFiltroValida(long janela) {
    return janela == 1 || (janela >= 3 && janela <= FILTRO_JANELA_MAX);
}

// Padrao de fabrica: FILTRO_JANELA se valido, senao 5.
inline int filtroJanela() {
    return janelaFiltroValida(FILTRO_JANELA) ? FILTRO_JANELA : 5;
}

inline int janelaDoFiltro(const FiltroMediana *f) {
    return janelaFiltroValida(f->janela) ? f->janela : filtroJanela();
}

// Esvazia a janela e define o tamanho (invalido = padrao de fabrica).
inline void filtroReiniciar(FiltroMediana *f, int janela = filtroJanela()) {
    f->quantidade = 0;
    f->proximo = 0;
    f->janela = janelaFiltroValida(janela) ? janela : filtroJanela();
}

// Acrescenta `valor` e devolve a mediana da janela. Com menos leituras que a janela,
// usa as que existem (par: media dos dois centrais). NAN: nao entra e devolve NAN.
inline float filtroMediana(FiltroMediana *f, float valor) {
    if (isnan(valor)) return NAN;
    int janela = janelaDoFiltro(f);
    if (janela == 1) return valor;
    if (f->quantidade > janela || f->quantidade < 0 || f->proximo < 0 || f->proximo >= janela) {
        filtroReiniciar(f, janela);
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

// ---------------------------------------------------------------------------
// Parametros de coleta fora do codigo: intervalo entre leituras e janela do filtro.
// Ficam na flash (Preferences, namespace "config", chaves "intervalo" e "janela") e
// se trocam pelo cabo: CT<{"cmd":"parametros","intervalo":20000,"filtroJanela":5}.
// Os #define abaixo sao so o padrao de fabrica (placa sem nada gravado).
// Intervalo: no minimo 15 s (o ThingSpeak gratis aceita 1 mensagem a cada 15 s) e no
// maximo 5 min (acima disso o painel passa a mostrar o sensor como sem leitura recente).
// ---------------------------------------------------------------------------
#ifndef INTERVALO_ENVIO_PADRAO_MS
#define INTERVALO_ENVIO_PADRAO_MS 20000UL
#endif
#define INTERVALO_ENVIO_MIN_MS 15000UL
#define INTERVALO_ENVIO_MAX_MS 300000UL

inline bool intervaloEnvioValido(long ms) {
    return ms >= (long)INTERVALO_ENVIO_MIN_MS && ms <= (long)INTERVALO_ENVIO_MAX_MS;
}

// Padrao de fabrica: INTERVALO_ENVIO_PADRAO_MS se valido, senao 20 s.
inline unsigned long intervaloEnvioPadrao() {
    return intervaloEnvioValido((long)INTERVALO_ENVIO_PADRAO_MS) ? INTERVALO_ENVIO_PADRAO_MS
                                                                 : 20000UL;
}

struct ParametrosColeta {
    unsigned long intervaloMs;
    int filtroJanela;
};

// Valores lidos da flash. Invalido (flash vazia = 0, ou valor fora da regra atual)
// volta ao padrao de fabrica.
inline ParametrosColeta parametrosDaFlashCore(unsigned long intervaloGravado, int janelaGravada) {
    ParametrosColeta p;
    p.intervaloMs = intervaloGravado <= INTERVALO_ENVIO_MAX_MS &&
                            intervaloEnvioValido((long)intervaloGravado)
                        ? intervaloGravado
                        : intervaloEnvioPadrao();
    p.filtroJanela = janelaFiltroValida(janelaGravada) ? janelaGravada : filtroJanela();
    return p;
}

enum class CampoJson { AUSENTE, OK, INVALIDO };

// Inteiro sem sinal em "chave":123 (sem aspas, sem ponto, sem expoente, ate 9 digitos).
// Chave ausente: AUSENTE. Qualquer outra forma (texto, negativo, 2.5, 1e5, null): INVALIDO.
inline CampoJson inteiroDoJsonCore(const std::string &json, const std::string &chave, long *valor) {
    std::string alvo = "\"" + chave + "\"";
    size_t pos = json.find(alvo);
    if (pos == std::string::npos) return CampoJson::AUSENTE;
    pos += alvo.size();
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    if (pos >= json.size() || json[pos] != ':') return CampoJson::INVALIDO;
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    size_t inicio = pos;
    long numero = 0;
    while (pos < json.size() && json[pos] >= '0' && json[pos] <= '9') {
        if (pos - inicio >= 9) return CampoJson::INVALIDO;
        numero = numero * 10 + (json[pos] - '0');
        pos++;
    }
    if (pos == inicio) return CampoJson::INVALIDO;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    if (pos < json.size() && json[pos] != ',' && json[pos] != '}') return CampoJson::INVALIDO;
    if (valor) *valor = numero;
    return CampoJson::OK;
}

// Comando "parametros": aplica em `p` os campos presentes ("intervalo" em ms e
// "filtroJanela"). Tudo ou nada: com qualquer campo invalido, `p` fica como estava.
// Devolve nullptr quando aceito, ou o codigo de erro da resposta CT>
// ("intervalo_invalido" | "janela_invalida"). Sem nenhum dos campos: so consulta.
inline const char *parametrosDoComandoCore(const std::string &json, ParametrosColeta *p) {
    ParametrosColeta novo = *p;
    long valor = 0;

    CampoJson intervalo = inteiroDoJsonCore(json, "intervalo", &valor);
    if (intervalo == CampoJson::INVALIDO ||
        (intervalo == CampoJson::OK && !intervaloEnvioValido(valor))) {
        return "intervalo_invalido";
    }
    if (intervalo == CampoJson::OK) novo.intervaloMs = (unsigned long)valor;

    CampoJson janela = inteiroDoJsonCore(json, "filtroJanela", &valor);
    if (janela == CampoJson::INVALIDO || (janela == CampoJson::OK && !janelaFiltroValida(valor))) {
        return "janela_invalida";
    }
    if (janela == CampoJson::OK) novo.filtroJanela = (int)valor;

    *p = novo;
    return nullptr;
}

// Falha que vale tentar de novo depois (a leitura fica na fila).
// So o dado recusado pelo contrato (400, 409, 413, 422) e descartado: reenviar
// o mesmo corpo da a mesma resposta. Todo o resto pode passar sozinho:
// - rede fora ou timeout (status <= 0) e servidor com erro (5xx);
// - 401 e 403: chave trocada no painel ou app parado no Azure (o App Service
//   parado responde 403 com pagina HTML). F4 em 24/11/2026 perdeu a seq 12230
//   assim, e 32 leituras foram descartadas com 401 antes de a chave ser
//   cadastrada de novo;
// - 404 (rota fora durante o deploy), 408 (timeout do servidor), 429 (limite).
inline bool falhaTemporaria(int status) {
    if (status <= 0 || status >= 500) return true;
    switch (status) {
        case 401: case 403: case 404: case 408: case 429: return true;
        default: return false;
    }
}

#endif
