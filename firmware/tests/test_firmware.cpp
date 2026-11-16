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
                "\"rssi\":-58,\"seq\":4294967295,\"medidoEm\":1790000000}");

    // seq 0 = firmware sem sequencia: o campo nao vai.
    montarPayloadCore(buffer, sizeof(buffer), "coldtrack-01", 12.4f, 81.0f, -58, 0, 0);
    ASSERT(std::string(buffer).find("seq") == std::string::npos);
    PASS();
}

int main() {
    std::cout << "=== Executando Testes Unitarios do Firmware (C++) ===\n";
    test_payload_com_rssi_negativo_e_medido_em();
    test_payload_com_rssi_positivo_vira_null();
    test_payload_com_seq();
    test_extrair_numero_do_json();
    test_classificacao_de_faixa_termica();
    test_classificacao_sem_limite_inferior();
    test_extrair_numero_com_espaco_e_texto_invalido();

    std::cout << "\nResultado: " << testes_passaram << "/" << total_testes << " testes passaram.\n";
    return (testes_passaram == total_testes) ? 0 : 1;
}

