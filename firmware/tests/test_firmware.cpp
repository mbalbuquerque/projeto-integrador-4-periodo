/**
 * Testes unitários automatizados da lógica de negócio do firmware em C++.
 * Executado nativamente no host (Linux x86_64) ou em CI via g++.
 */

#include <iostream>
#include <cassert>
#include <cmath>
#include <string>
#include "../coldtrack/payload_core.h"

int total_testes = 0;
int testes_passaram = 0;

#define TEST(nome) \
    total_testes++; \
    std::cout << "  RUN: " << nome << " ... ";

#define ASSERT(cond) \
    if (!(cond)) { \
        std::cout << "FAILED! (" #cond " at line " << __LINE__ << ")\n"; \
        return; \
    }

#define PASS() \
    testes_passaram++; \
    std::cout << "OK\n";

void test_payload_com_rssi_negativo_e_medido_em() {
    TEST("montarPayloadCore com RSSI e medidoEm");
    char buffer[256];
    montarPayloadCore(buffer, sizeof(buffer), "coldtrack-01", 12.4f, 81.0f, -58, 1790000000);
    std::string s(buffer);

    ASSERT(s.find("\"deviceId\":\"coldtrack-01\"") != std::string::npos);
    ASSERT(s.find("\"temperatura\":12.4") != std::string::npos);
    ASSERT(s.find("\"umidade\":81.0") != std::string::npos);
    ASSERT(s.find("\"rssi\":-58") != std::string::npos);
    ASSERT(s.find("\"medidoEm\":1790000000") != std::string::npos);
    PASS();
}

void test_payload_origem() {
    TEST("montarPayloadCore leva origem (padrao placa, simulador quando pedido)");
    char buffer[256];
    montarPayloadCore(buffer, sizeof(buffer), "coldtrack-01", 12.4f, 81.0f, -58, 1790000000, 5);
    ASSERT(std::string(buffer).find("\"origem\":\"placa\"") != std::string::npos);
    montarPayloadCore(buffer, sizeof(buffer), "coldtrack-01", 12.4f, 81.0f, -58, 1790000000, 5,
                      "simulador");
    ASSERT(std::string(buffer).find("\"origem\":\"simulador\"") != std::string::npos);
    montarPayloadCore(buffer, sizeof(buffer), "coldtrack-01", 12.4f, 81.0f, -58, 0, 0, "");
    ASSERT(std::string(buffer).find("\"origem\":\"placa\"") != std::string::npos);
    PASS();
}

void test_payload_com_rssi_positivo_vira_null() {
    TEST("montarPayloadCore com RSSI positivo vai como null");
    char buffer[256];
    montarPayloadCore(buffer, sizeof(buffer), "coldtrack-01", 10.0f, 70.0f, 0, 0);
    std::string s(buffer);

    ASSERT(s.find("\"rssi\":null") != std::string::npos);
    ASSERT(s.find("medidoEm") == std::string::npos);
    PASS();
}

void test_extrair_numero_do_json() {
    TEST("extrairNumeroJson le valores numericos e trata null/ausente");
    std::string json = "{\"min\":10.5, \"max\": 13.0, \"margem\":null}";

    float minVal = extrairNumeroJson(json, "min");
    ASSERT(std::fabs(minVal - 10.5f) < 0.001f);

    float maxVal = extrairNumeroJson(json, "max");
    ASSERT(std::fabs(maxVal - 13.0f) < 0.001f);

    float margemVal = extrairNumeroJson(json, "margem");
    ASSERT(std::isnan(margemVal));

    float ausente = extrairNumeroJson(json, "inexistente");
    ASSERT(std::isnan(ausente));
    PASS();
}

void test_classificacao_de_faixa_termica() {
    TEST("classificarFaixa classifica normal, atencao e critico");
    // Manga: 10.0 a 13.0 °C, margem 3.0 °C
    float min = 10.0f, max = 13.0f, margem = 3.0f;

    // Normal (10 a 13)
    ASSERT(classificarFaixa(11.5f, min, max, margem) == StatusTermico::NORMAL);
    ASSERT(classificarFaixa(10.0f, min, max, margem) == StatusTermico::NORMAL);
    ASSERT(classificarFaixa(13.0f, min, max, margem) == StatusTermico::NORMAL);

    // Atenção (7 a 10 ou 13 a 16)
    ASSERT(classificarFaixa(8.5f, min, max, margem) == StatusTermico::ATENCAO);
    ASSERT(classificarFaixa(15.0f, min, max, margem) == StatusTermico::ATENCAO);

    // Crítico (< 7 ou > 16)
    ASSERT(classificarFaixa(5.0f, min, max, margem) == StatusTermico::CRITICO);
    ASSERT(classificarFaixa(20.0f, min, max, margem) == StatusTermico::CRITICO);

    // NaN
    ASSERT(classificarFaixa(NAN, min, max, margem) == StatusTermico::CRITICO);
    PASS();
}

void test_classificacao_sem_limite_inferior() {
    TEST("classificarFaixa sem limite inferior (perfil padrao do firmware)");
    // Faixa padrao gravada na placa: sem minimo, normal ate 15, margem 5.
    float min = NAN, max = 15.0f, margem = 5.0f;

    ASSERT(classificarFaixa(-30.0f, min, max, margem) == StatusTermico::NORMAL);
    ASSERT(classificarFaixa(15.0f, min, max, margem) == StatusTermico::NORMAL);
    ASSERT(classificarFaixa(18.0f, min, max, margem) == StatusTermico::ATENCAO);
    ASSERT(classificarFaixa(20.0f, min, max, margem) == StatusTermico::ATENCAO);
    ASSERT(classificarFaixa(24.5f, min, max, margem) == StatusTermico::CRITICO);
    PASS();
}

void test_extrair_numero_com_espaco_e_texto_invalido() {
    TEST("extrairNumeroJson pula espaco e devolve NAN para texto invalido");
    // A nuvem (json.dumps do Python) responde com espaco depois dos dois-pontos.
    std::string json = "{\"faixa\": {\"min\": null, \"max\": 13.0, \"margem\": \"x\"}}";

    ASSERT(std::isnan(extrairNumeroJson(json, "min")));
    ASSERT(std::fabs(extrairNumeroJson(json, "max") - 13.0f) < 0.001f);
    ASSERT(std::isnan(extrairNumeroJson(json, "margem")));
    PASS();
}

void test_payload_com_seq() {
    TEST("montarPayloadCore com numero de sequencia");
    char buffer[256];
    montarPayloadCore(buffer, sizeof(buffer), "coldtrack-01", 12.4f, 81.0f, -58, 1790000000, 4294967295u);
    std::string s(buffer);

    ASSERT(s == "{\"deviceId\":\"coldtrack-01\",\"temperatura\":12.4,\"umidade\":81.0,"
                "\"rssi\":-58,\"seq\":4294967295,\"medidoEm\":1790000000,"
                "\"origem\":\"placa\"}");

    // seq 0 = firmware sem sequencia: o campo nao vai.
    montarPayloadCore(buffer, sizeof(buffer), "coldtrack-01", 12.4f, 81.0f, -58, 0, 0);
    ASSERT(std::string(buffer).find("seq") == std::string::npos);
    PASS();
}

void test_heartbeat() {
    TEST("montarHeartbeatCore com e sem seq/RSSI");
    char buffer[200];
    montarHeartbeatCore(buffer, sizeof(buffer), "coldtrack-01", "sensor_falha",
                        "2026.11.17.2", -61, 42);
    ASSERT(std::string(buffer) ==
           "{\"deviceId\":\"coldtrack-01\",\"motivo\":\"sensor_falha\","
           "\"fw\":\"2026.11.17.2\",\"rssi\":-61,\"seq\":42}");

    // Simulador (RSSI >= 0) e placa que ainda nao leu nada (seq 0).
    montarHeartbeatCore(buffer, sizeof(buffer), "coldtrack-01", "sensor_falha",
                        "2026.11.17.2", 0, 0);
    ASSERT(std::string(buffer) ==
           "{\"deviceId\":\"coldtrack-01\",\"motivo\":\"sensor_falha\","
           "\"fw\":\"2026.11.17.2\",\"rssi\":null}");
    PASS();
}

void test_url_do_heartbeat() {
    TEST("urlHeartbeatCore troca /telemetria por /heartbeat");
    ASSERT(urlHeartbeatCore("https://x.azurewebsites.net/api/telemetria") ==
           "https://x.azurewebsites.net/api/heartbeat");
    ASSERT(urlHeartbeatCore("https://x/api/telemetria?code=1") == "https://x/api/heartbeat?code=1");
    ASSERT(urlHeartbeatCore("https://x/api/outra").empty());
    PASS();
}

void test_agenda_fixa_de_20_s() {
    TEST("proximoCicloCore conta do inicio ao inicio");
    // Envio de 15 s nao empurra o ciclo: o proximo continua 20 s depois do inicio.
    unsigned long previsto = 20000;
    ASSERT(proximoCicloCore(20000, previsto, 20000, false) == 40000);
    // Comecou 3 s atrasado (prints, sensor): o seguinte nao herda o atraso.
    ASSERT(proximoCicloCore(43000, 40000, 20000, false) == 60000);
    // Parado mais de um intervalo inteiro: recomeca de agora, sem rajada.
    ASSERT(proximoCicloCore(130000, 60000, 20000, false) == 150000);
    // Pedido de leitura ja (configuracao pelo cabo).
    ASSERT(proximoCicloCore(5000, 60000, 20000, true) == 25000);
    // Volta do millis() (~49 dias).
    unsigned long quase = 0xFFFFFFFFUL - 1000;
    unsigned long depois = proximoCicloCore(quase, quase, 20000, false);
    ASSERT(depois == quase + 20000UL);
    ASSERT(!cicloVencidoCore(quase + 19999UL, depois));
    ASSERT(cicloVencidoCore(quase + 20000UL, depois));
    ASSERT(cicloVencidoCore(18999, 18999));
    ASSERT(!cicloVencidoCore(18998, 18999));
    PASS();
}

void test_linha_da_fila_sem_relogio() {
    TEST("linhaComMsCore le e tira o campo ms");
    unsigned long ms = 0;
    std::string sem;
    ASSERT(linhaComMsCore("{\"deviceId\":\"x\",\"temperatura\":1.0,\"seq\":7,\"ms\":123456}", &ms, &sem));
    ASSERT(ms == 123456UL);
    ASSERT(sem == "{\"deviceId\":\"x\",\"temperatura\":1.0,\"seq\":7}");
    ASSERT(!linhaComMsCore("{\"deviceId\":\"x\",\"seq\":7,\"medidoEm\":1790000000}", &ms, &sem));
    ASSERT(!linhaComMsCore("{\"deviceId\":\"x\",\"ms\":}", &ms, &sem));
    PASS();
}

void test_filtro_mediana_descarta_pico_isolado() {
    TEST("filtroMediana descarta um pico isolado");
    FiltroMediana f; filtroReiniciar(&f);
    float saida = 0;
    const float entrada[] = {30.0f, 30.2f, 30.1f, 45.0f, 30.2f};  // 45.0 = pico
    for (float v : entrada) saida = filtroMediana(&f, v);
    ASSERT(fabsf(saida - 30.2f) < 0.001f);
    PASS();
}

void test_filtro_mediana_janela_parcial_e_par() {
    TEST("filtroMediana com janela ainda incompleta");
    FiltroMediana f; filtroReiniciar(&f);
    ASSERT(fabsf(filtroMediana(&f, 31.0f) - 31.0f) < 0.001f);   // 1 leitura
    ASSERT(fabsf(filtroMediana(&f, 33.0f) - 32.0f) < 0.001f);   // 2: media dos centrais
    ASSERT(fabsf(filtroMediana(&f, 29.0f) - 31.0f) < 0.001f);   // 3: mediana
    PASS();
}

void test_filtro_mediana_janela_desliza() {
    TEST("filtroMediana descarta a leitura mais antiga");
    FiltroMediana f; filtroReiniciar(&f);
    float saida = 0;
    for (int i = 0; i < 5; i++) saida = filtroMediana(&f, 20.0f);
    ASSERT(fabsf(saida - 20.0f) < 0.001f);
    for (int i = 0; i < 3; i++) saida = filtroMediana(&f, 25.0f);  // 3 de 5 ja sao 25
    ASSERT(fabsf(saida - 25.0f) < 0.001f);
    ASSERT(f.quantidade == 5);
    PASS();
}

void test_filtro_mediana_nan_nao_entra() {
    TEST("filtroMediana ignora NAN e nao o grava como valido");
    FiltroMediana f; filtroReiniciar(&f);
    filtroMediana(&f, 30.0f);
    filtroMediana(&f, 31.0f);
    ASSERT(isnan(filtroMediana(&f, NAN)));
    ASSERT(f.quantidade == 2);
    ASSERT(fabsf(filtroMediana(&f, 32.0f) - 31.0f) < 0.001f);
    PASS();
}

void test_filtro_mediana_estado_corrompido_reinicia() {
    TEST("filtroMediana recupera estado fora da faixa");
    FiltroMediana f; f.quantidade = 99; f.proximo = -4;
    ASSERT(fabsf(filtroMediana(&f, 28.5f) - 28.5f) < 0.001f);
    ASSERT(f.quantidade == 1);
    PASS();
}
int main() {
    std::cout << "=== Executando Testes Unitarios do Firmware (C++) ===\n";
    test_agenda_fixa_de_20_s();
    test_linha_da_fila_sem_relogio();
    test_heartbeat();
    test_url_do_heartbeat();
    test_payload_com_rssi_negativo_e_medido_em();
    test_payload_origem();
    test_payload_com_rssi_positivo_vira_null();
    test_payload_com_seq();
    test_extrair_numero_do_json();
    test_classificacao_de_faixa_termica();
    test_classificacao_sem_limite_inferior();
    test_extrair_numero_com_espaco_e_texto_invalido();
    test_filtro_mediana_descarta_pico_isolado();
    test_filtro_mediana_janela_parcial_e_par();
    test_filtro_mediana_janela_desliza();
    test_filtro_mediana_nan_nao_entra();
    test_filtro_mediana_estado_corrompido_reinicia();

    std::cout << "\nResultado: " << testes_passaram << "/" << total_testes << " testes passaram.\n";
    return (testes_passaram == total_testes) ? 0 : 1;
}

