
# FACULDADE SENAC PE
## PROJETO INTEGRADOR
## PROFESSOR ORIENTADOR ARNOT CAIADO

## EQUIPE: ENZO ANTÔNIO, EVERSON, EMERSON LUIZ, GABRIEL EDUARDO, JOSÉ ALLAMBERG, MARCELO BARBOSA



# 🚚 ColdTrack Edge

Projeto desenvolvido para o **Projeto Integrador – 4º Período**, com foco no monitoramento de **temperatura e umidade durante o transporte refrigerado de mercadorias**.

## 🎯 Objetivo

Desenvolver um nó sensor IoT capaz de monitorar as condições ambientais no interior de um compartimento refrigerado, realizando processamento local e envio de telemetria para a nuvem.

## 🛠️ Tecnologias e Componentes

- ESP32-C3
- Sensor DHT11
- LEDs de sinalização
- Wi-Fi
- Microsoft Azure (Functions, Cosmos DB, Storage)
- Wokwi
- Arduino Framework (C/C++)

## 🚦 Sinalização Local

O protótipo utiliza três LEDs para indicar o estado das condições monitoradas:

- 🟢 **Verde:** condição normal
- 🟡 **Amarelo:** atenção
- 🔴 **Vermelho:** condição crítica ou falha

Os limites utilizados durante a fase inicial são demonstrativos e poderão ser configurados conforme o tipo de mercadoria transportada.

## ☁️ Telemetria

O ESP32-C3 envia cada leitura em JSON, por HTTPS, para uma Azure Function que valida os dados e grava no Azure Cosmos DB:

```json
{"deviceId": "coldtrack-01", "temperatura": 12.4, "umidade": 81.0, "rssi": -58, "medidoEm": 1790000000}
```

Sem conexão, as leituras ficam guardadas na memória flash do ESP32 e são reenviadas quando a conexão volta. Detalhes da API em [`cloud/function/README.md`](cloud/function/README.md).

Dashboard publicado: https://stcoldtrackweb7319.z15.web.core.windows.net

## 🔐 Segurança

Credenciais Wi-Fi e chaves de API não serão armazenadas diretamente no código-fonte público.

As credenciais ficam em `secrets.h`, ignorado pelo Git. Use `secrets.example.h` como modelo.

## ♻️ Design Circular

A versão física utilizará um gabinete produzido a partir de embalagem reaproveitada, com aberturas para circulação de ar junto ao sensor e passagem para alimentação USB-C.

## 🚧 Status

Projeto em desenvolvimento.

### Etapa atual

- [x] Definição da arquitetura
- [x] Simulação ESP32-C3 no Wokwi
- [x] Leitura de temperatura e umidade
- [x] Sistema de alerta com LEDs
- [x] Envio em JSON via HTTPS para o Azure
- [x] Armazenamento das leituras sem conexão e reenvio
- [x] Dashboard web publicado no Azure
- [ ] Montagem física
- [ ] Gabinete reciclado
- [ ] Testes de campo
- [ ] Relatório técnico

---

**Projeto Integrador – 4º Período**  
**2026.2**
