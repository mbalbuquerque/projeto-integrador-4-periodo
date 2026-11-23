# Coleta da placa física no Cosmos DB (perda medida por sequência)

Gerado por `descrever_cosmos.py` a partir de `dados/cosmos_leituras.csv` (container `leituras` da API em produção, dispositivo `coldtrack-0e0b2c`). Complementa o `relatorio.md` (canal ThingSpeak). Dado real da placa; nada estimado à mão.

## Resultado

| item | valor |
|---|---|
| primeira leitura (UTC) | 2026-11-17 06:46:41 |
| última leitura (UTC) | 2026-11-20 08:10:34 |
| período | 73.40 h |
| leituras gravadas | 11710 |
| `seq` | 308 a 12118, 0 repetidas |
| números de `seq` faltantes | 101 |
| **taxa de perda** (faltantes ÷ faixa de `seq`) | **0.86%** |
| leituras esperadas no período (a cada 20 s) | 13212 |
| **disponibilidade** (gravadas ÷ esperadas) | **88.6%** |
| horas cobertas (soma dos trechos sem lacuna) | 66.20 h |
| maior trecho contínuo | 10.26 h (2026-11-17 10:27 a 2026-11-17 20:42 UTC) |

A perda mede só o que a placa numerou e a API não recebeu. O tempo com a placa desligada ou sem rede não gera `seq`, e entra na disponibilidade, não na perda. Meta de perda: no máximo 1% (prévia técnica, seção 4.2); aqui o período é maior que as 24 h exigidas, mas não é um teste controlado de 24 h seguidas.

## Lacunas maiores que 2 min

| de (UTC) | até (UTC) | duração |
|---|---|---|
| 2026-11-19 11:08:55 | 2026-11-19 15:55:35 | 286.7 min |
| 2026-11-18 17:18:01 | 2026-11-18 17:39:22 | 21.4 min |
| 2026-11-19 10:05:40 | 2026-11-19 10:25:36 | 19.9 min |
| 2026-11-17 10:16:10 | 2026-11-17 10:24:10 | 8.0 min |
| 2026-11-18 14:40:41 | 2026-11-18 14:43:21 | 2.7 min |
| 2026-11-17 20:42:35 | 2026-11-17 20:44:55 | 2.3 min |
