# Medições de campo com os dados já gravados (sem a placa ligada)

Gerado por `medir_campo.py` a partir do export da coleção `leituras` do Cosmos DB (dispositivo `coldtrack-0e0b2c`). Tudo sai do dado; nada é estimado à mão.

## Período

| item | valor |
|---|---|
| primeira leitura (medidoEm, UTC) | 2026-11-17 06:46:41 |
| última leitura (medidoEm, UTC) | 2026-11-20 08:10:34 |
| duração | 73,4 h |
| leituras gravadas (com `seq`) | 11710 |
| `seq` esperados (do menor ao maior) | 11811 |
| `seq` faltantes | 101 (0,86%) |

## 1. Perda em janelas de 24 h (pela sequência)

Janelas deslizantes de 24 h, com passo de 1 h, por `medidoEm`. Perda = `seq` faltantes ÷ `seq` esperados na janela. Placa desligada não é perda: a numeração (guardada na flash) continua de onde parou. A queda do aparelho aparece na disponibilidade, não aqui.

| item | valor |
|---|---|
| janelas de 24 h analisadas | 50 |
| janelas com perda ≤ 1% | 23 de 50 (46,00%) |
| mediana da perda | 1,12% |
| melhor janela | 0,00% (17/11 10:46:41 a 18/11 10:46:41 UTC; 0 faltantes de 4213) |
| pior janela | 1,96% (18/11 16:46:41 a 19/11 16:46:41 UTC; 63 faltantes de 3212) |
| disponibilidade na janela (leituras ÷ 4.320 por 24 h), mediana | 92,49% |
| disponibilidade na janela, pior | 72,89% |

Meta da entrega final: perda ≤ 1% em 24 h. 27 janela(s) acima de 1%.

### Onde está a perda

32 buraco(s) na numeração somam 101 leituras. Os maiores:

| faltantes | entre (UTC) | `seq` seguinte |
|---|---|---|
| 63 | 18/11 17:18:01 a 18/11 17:39:22 | 6352 |
| 4 | 20/11 04:48:33 a 20/11 04:50:13 | 11534 |
| 3 | 20/11 04:31:33 a 20/11 04:32:53 | 11483 |
| 3 | 20/11 05:09:53 a 20/11 05:11:13 | 11594 |
| 1 | 17/11 10:25:43 a 17/11 10:27:00 | 923 |

O maior buraco concentra 62,38% de toda a perda. O dado não registra a causa.

## 2. Latência placa → banco

`recebidoEm` − `medidoEm`. O horário de medição vem da placa (NTP) e o de recebimento da API; pequena diferença de relógio entra na conta. Tempo real = atraso menor que 60 s; reenvio de buffer = atraso de 60 s ou mais.

| grupo | leituras | mediana (s) | p95 (s) | p99 (s) | máximo (s) |
|---|---|---|---|---|---|
| todas | 11710 | 4,0 | 1755,7 | 8675,5 | 10015,8 |
| tempo real (< 60 s) | 10692 | 3,9 | 7,8 | 19,1 | 58,8 |
| reenvio de buffer (≥ 60 s) | 1018 | 3698,4 | 9377,3 | 9902,8 | 10015,8 |

Leituras com atraso negativo (relógio da placa à frente do servidor): 0.

## 3. Guardar e reenviar (R2) em campo

Leituras entregues com atraso ≥ 60 s: **1018** de 11710 (8,69%), em **21** reenvio(s) de `seq` consecutivo. Cada grupo é um trecho que a placa guardou sem rede e entregou depois, mantendo o horário da medição.

Maiores reenvios:

| `seq` | leituras | medidas entre (UTC) | recebidas entre (UTC) | maior atraso | em ordem |
|---|---|---|---|---|---|
| 6352 a 6992 | 641 | 18/11 17:39:22 a 18/11 21:46:21 | 18/11 20:26:17 a 18/11 21:47:24 | 166,9 min | sim |
| 7027 a 7129 | 103 | 18/11 21:59:00 a 18/11 22:36:41 | 18/11 22:30:18 a 18/11 22:38:35 | 31,3 min | sim |
| 7276 a 7336 | 61 | 18/11 23:26:40 a 18/11 23:49:20 | 18/11 23:38:20 a 18/11 23:50:29 | 12,4 min | sim |
| 5765 a 5801 | 37 | 18/11 14:00:41 a 18/11 14:14:22 | 18/11 14:11:14 a 18/11 14:16:22 | 10,6 min | sim |
| 6191 a 6225 | 35 | 18/11 16:38:41 a 18/11 16:52:01 | 18/11 16:48:58 a 18/11 16:53:05 | 10,3 min | sim |
| 6010 a 6037 | 28 | 18/11 15:30:01 a 18/11 15:40:21 | 18/11 15:33:14 a 18/11 15:41:40 | 6,6 min | sim |
| 5211 a 5228 | 18 | 18/11 10:52:22 a 18/11 10:59:02 | 18/11 10:57:01 a 18/11 11:00:03 | 4,7 min | sim |
| 7346 a 7360 | 15 | 18/11 23:53:00 a 18/11 23:58:00 | 18/11 23:57:04 a 18/11 23:59:02 | 4,1 min | sim |

## O que este relatório não mede

- Latência ao vivo com estímulo: medida com a placa em 24/11, fora deste relatório (`docs/qa/relatorio-de-testes.md`, #126).
- Watchdog travando na placa física (#124), F4 com reenvio pela placa (#121) e F6 real (#123).
- A causa de cada reenvio (queda de Wi-Fi, API fora, reinício): o dado não registra o motivo.
- A última etapa, do banco até aparecer no painel, não está neste dado: ver `RESILIENCIA.md`.
