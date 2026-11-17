# Análise de dados climáticos — rota Petrolina → Suape

Scripts de coleta, limpeza e análise exploratória dos dados horários das estações
automáticas do INMET ao longo da rota do transporte refrigerado, com um modelo
preliminar de risco térmico.

Resultado atual: [relatorio.md](relatorio.md).

## Como rodar

```bash
cd analise
pip install -r requirements.txt
python baixar_inmet.py 2020 2021 2022 2023 2024 2025   # ~600 MB de download, salva só a rota
python limpar.py                                        # gera dados/inmet_rota_horario.csv
python explorar.py                                      # gera figuras/ e relatorio.md
python exportar_modelo.py                               # gera ../cloud/function/modelo_risco.json (rota /api/predict)
```

A pasta `dados/` não vai para o Git: os scripts baixam e regeneram tudo.

## Fonte

INMET — Banco de dados meteorológicos, dados históricos anuais das estações automáticas
(portal.inmet.gov.br/dadoshistoricos). Estações usadas: A307 Petrolina, A329 Cabrobó,
A370 Salgueiro, A350 Serra Talhada, A309 Arcoverde, A341 Caruaru e A301 Recife.

## Arquivos

| arquivo | função |
|---|---|
| `baixar_inmet.py` | baixa o pacote anual do INMET e guarda só as estações da rota |
| `limpar.py` | padroniza as colunas, converte para o horário de Brasília e descarta valores ausentes ou impossíveis |
| `explorar.py` | calcula os indicadores, gera as figuras, treina e avalia o modelo preliminar, escreve o relatório |
| `exportar_modelo.py` | exporta a tabela do modelo (treino 2019–2022) e as métricas para `cloud/function/modelo_risco.json`, lido pela rota `/api/predict` |

## Base da placa física (`sensor/`)

Leituras reais da placa ESP32-C3 (MQTT, a cada ~20 s), lidas do canal público ThingSpeak 3515173
(temperatura, umidade, RSSI). Descreve cobertura, lacunas, inválidos e estatística (requisito IOT-06).

```bash
cd analise/sensor
python baixar_thingspeak.py   # baixa o canal inteiro para dados/thingspeak_3515173.csv (versionado)
python descrever.py           # gera relatorio.md e figuras/
```

Resultado: [sensor/relatorio.md](sensor/relatorio.md). O CSV está no Git por ser dado real e público
(coluna `origem` = `placa_fisica_thingspeak`). Lacuna = intervalo entre leituras maior que 2x o
período esperado (40 s). Os testes (`sensor/test_sensor_*.py`) usam dados sintéticos e rodam no CI.
