
# EQUIPE: ANTONIO HENZO, EVERSON, EMERSON LUIZ, GABRIEL EDUARDO, JOSÉ ALANBERG, MARCELO BARBOSA



# 🚚 ColdTrack Edge

Projeto desenvolvido para o **Projeto Integrador – 4º Período**, com foco no monitoramento de **temperatura e umidade durante o transporte refrigerado de mercadorias**.

## 🎯 Objetivo

Desenvolver um nó sensor IoT capaz de monitorar as condições ambientais no interior de um compartimento refrigerado, realizando processamento local e envio de telemetria para a nuvem.

## 🛠️ Tecnologias e Componentes

- ESP32-C3
- Sensor DHT11
- LEDs de sinalização
- Wi-Fi
- ThingSpeak
- Wokwi
- Arduino Framework (C/C++)

## 🚦 Sinalização Local

O protótipo utiliza três LEDs para indicar o estado das condições monitoradas:

- 🟢 **Verde:** condição normal
- 🟡 **Amarelo:** atenção
- 🔴 **Vermelho:** condição crítica ou falha

Os limites utilizados durante a fase inicial são demonstrativos e poderão ser configurados conforme o tipo de mercadoria transportada.

## ☁️ Telemetria

Os dados serão enviados pelo ESP32-C3 via Wi-Fi para a plataforma ThingSpeak:

- **Field 1:** Temperatura (°C)
- **Field 2:** Umidade Relativa (%)
- **Field 3:** RSSI Wi-Fi (dBm)

## 🔐 Segurança

Credenciais Wi-Fi e chaves de API não serão armazenadas diretamente no código-fonte público.

O projeto utilizará arquivo separado para configuração das credenciais, ignorado pelo Git.

## ♻️ Design Circular

A versão física utilizará um gabinete produzido a partir de embalagem reaproveitada, com aberturas para circulação de ar junto ao sensor e passagem para alimentação USB-C.

## 🚧 Status

Projeto em desenvolvimento.

### Etapa atual

- [x] Definição da arquitetura
- [x] Simulação ESP32-C3 no Wokwi
- [x] Leitura de temperatura e umidade
- [x] Sistema de alerta com LEDs
- [x] Criação do canal ThingSpeak
- [ ] Integração Wokwi → ThingSpeak
- [ ] Montagem física
- [ ] Gabinete reciclado
- [ ] Testes de campo
- [ ] Relatório técnico

---

**Projeto Integrador – 4º Período**  
**2026**
