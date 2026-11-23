# Base da placa física: descrição e qualidade

Gerado por `descrever.py` a partir de `dados/thingspeak_3515173.csv` (canal público ThingSpeak 3515173, placa ESP32-C3 via MQTT, dado real). Requisito IOT-06.

## Cobertura

| item | valor |
|---|---|
| primeira leitura (UTC) | 2026-09-29 18:36:01 |
| última leitura (UTC) | 2026-11-20 08:10:37 |
| período entre a primeira e a última | 51.57 dias |
| leituras | 12730 |
| leituras esperadas no período (a cada 20 s) | 222764 |
| completude em relação ao esperado | 5.71% |
| dias de calendário (UTC-3) com ao menos uma leitura | 11 |
| **horas cobertas** (soma dos trechos sem lacuna) | **69.04 h** |
| **maior janela contínua** | **2.57 h** (2026-11-20 02:30 a 2026-11-20 05:04 UTC, 454 leituras) |

## Veredito sobre a meta de 48 h

**Não atendida como trecho contínuo; atendida pela soma das horas cobertas.** A maior janela sem lacuna tem 2.57 h, abaixo das 48 h seguidas. A soma das horas cobertas é 69.04 h (acima das 48 h), em trechos separados por lacunas (placa desligada ou sem rede; a causa não consta nos dados). O período entre a primeira e a última leitura é maior que a cobertura real.

## Intervalo entre leituras

| métrica | valor |
|---|---|
| esperado | 20 s |
| mediana real | 20.00 s |
| p95 real | 40.00 s |

## Faltantes (lacunas)

Lacuna = intervalo entre duas leituras consecutivas maior que 2x o esperado (40 s).

| item | valor |
|---|---|
| lacunas | 492 |
| duração total das lacunas | 48.69 dias |
| fração do período em lacuna | 94.42% |
| trechos contínuos | 493 |
| leituras ausentes no período (esperadas menos presentes) | 210034 (94.29% das esperadas) |

Dez maiores lacunas:

| de (UTC) | até (UTC) | duração |
|---|---|---|
| 2026-10-09 00:49:59 | 2026-11-08 22:04:56 | 30.89 dias |
| 2026-11-09 23:15:37 | 2026-11-16 22:03:19 | 6.95 dias |
| 2026-09-29 20:06:15 | 2026-10-04 20:05:57 | 5.00 dias |
| 2026-10-06 15:46:08 | 2026-10-08 17:46:31 | 2.08 dias |
| 2026-10-04 20:29:29 | 2026-10-06 14:57:24 | 1.77 dias |
| 2026-11-08 22:12:18 | 2026-11-09 22:50:37 | 1.03 dias |
| 2026-11-19 11:08:59 | 2026-11-19 15:55:39 | 4.78 h |
| 2026-11-18 17:18:06 | 2026-11-18 20:26:47 | 3.14 h |
| 2026-11-16 22:34:15 | 2026-11-17 01:32:14 | 2.97 h |
| 2026-11-18 21:58:47 | 2026-11-18 22:30:37 | 0.53 h |

Maiores trechos contínuos:

| início (UTC) | fim (UTC) | duração | leituras |
|---|---|---|---|
| 2026-11-20 02:30:59 | 2026-11-20 05:04:56 | 2.57 h | 454 |
| 2026-11-18 01:08:04 | 2026-11-18 03:35:23 | 2.46 h | 434 |
| 2026-11-17 07:57:36 | 2026-11-17 10:16:12 | 2.31 h | 407 |
| 2026-11-17 20:44:58 | 2026-11-17 22:55:57 | 2.18 h | 389 |
| 2026-11-17 22:56:38 | 2026-11-18 01:07:23 | 2.18 h | 385 |
| 2026-11-17 17:48:39 | 2026-11-17 19:49:38 | 2.02 h | 353 |
| 2026-11-19 08:06:04 | 2026-11-19 10:05:45 | 1.99 h | 358 |
| 2026-11-19 17:45:59 | 2026-11-19 19:36:58 | 1.85 h | 321 |
| 2026-11-18 04:51:47 | 2026-11-18 06:29:43 | 1.63 h | 290 |
| 2026-11-20 05:05:37 | 2026-11-20 06:29:56 | 1.41 h | 246 |

## Inválidos

Faixa física do DHT11: temperatura 0 a 50 °C, umidade 20 a 90 %. Faixa aceita pela API (`cloud/function/contrato.py`): temperatura -40 a 80 °C, umidade 0 a 100 %. Inválido = NaN ou fora da faixa.

| variável | NaN | fora da faixa DHT11 (inclui NaN) | fora da faixa da API (inclui NaN) |
|---|---|---|---|
| temperatura | 0 | 0 (0.00%) | 0 (0.00%) |
| umidade | 0 | 0 (0.00%) | 0 (0.00%) |
| rssi | 1 | n/a | n/a |
| **leituras com ao menos uma variável inválida** | | **0 (0.00%)** | **0 (0.00%)** |

## Estatística descritiva

| variável | n | mín | Q1 | mediana | Q3 | máx | média | desvio |
|---|---|---|---|---|---|---|---|---|
| temperatura (°C) | 12730 | 21.40 | 32.80 | 34.20 | 35.20 | 39.50 | 34.38 | 1.97 |
| umidade (%) | 12730 | 43.00 | 48.00 | 51.00 | 55.00 | 77.00 | 51.13 | 4.47 |
| rssi (dBm) | 12729 | -78.00 | -57.00 | -52.00 | -50.00 | -16.00 | -52.87 | 4.62 |

![série](figuras/serie.png)

![janelas](figuras/janelas.png)

Limpeza passo a passo da base do Cosmos (outro dispositivo, sem `seq`, duplicados, fora de faixa, instante repetido), com contagens antes e depois: `limpeza.md`.
