# Model card: thermal risk model

## Purpose

Estimates the probability that the outdoor air temperature exceeds 30 °C for a given month and
hour of the day along the Petrolina → Suape route. The dashboard shows it (the mobile app can call the same route) to help
the team choose departure times and decide when to reinforce monitoring of a refrigerated cargo.
It supports a human decision; it does not trigger any automatic action.

## Model

Climatological model: for each (month, hour) pair, the share of hours above 30 °C in the training
years. A cell with no training hour falls back to the baseline. Code: `analise/explorar.py`
(analysis and evaluation) and `analise/exportar_modelo.py` (export). Report:
`analise/relatorio.md`.

- Version: `clima-a307-30c-v1`.
- Artifact: `cloud/function/modelo_risco.json`, a 12 × 24 probability table plus the number of
  training hours behind each cell, the baseline, the metrics and the risk levels. It is a few
  kilobytes and needs no machine-learning library at runtime.

## Serving

`GET /api/predict?mes=<1..12>&hora=<0..23>` (operator or manager token). It returns the model
probability, the risk level, the baseline probability for comparison, the training hours behind
the cell, the model version and both Brier scores. Details: `docs/api.md` and the OpenAPI
specification (`/api/openapi.json`).

Risk levels: `baixo` (low) up to 0.20, `moderado` (moderate) up to 0.50, `alto` (high) above
0.50. The 0.50 cut is the same one used to measure accuracy below.

## Data

- Source: INMET automatic stations, hourly data, 2019–2025 (A307 Petrolina as the main station).
- Hours without a valid reading were discarded, never filled.
- Training: 2019–2022 (22,875 hours). Test: 2023–2025 (9,278 hours). The split is temporal, so the
  model is evaluated on years it has not seen. The served table is the one trained on 2019–2022,
  the same one that was evaluated.

## Evaluation (test years)

| Metric | Value |
|---|---|
| Brier score, model | 0.091 |
| Brier score, naive baseline (overall share of hours above 30 °C in training, 0.214) | 0.202 |
| Error reduction over the baseline | 55% |
| Accuracy when flagging "risk hour" (probability ≥ 50%) | 87% |
| Share of hours above 30 °C that the model flagged | 62% |

## Limitations

- **It does not use the readings of the project's own sensor.** The model is trained on a public
  INMET weather station (A307 Petrolina), so it estimates the outdoor temperature at the origin,
  not the temperature inside the cargo box, and not the conditions along the rest of the route.
- It describes the typical pattern, not the weather forecast of the day.
- Public stations have long gaps (for example, Petrolina has no valid hours in 2025), so some
  months are estimated from fewer years. `horasDeHistorico` in the answer shows the sample
  size of each cell.
- It misses part of the hot hours: only 62% of the test hours above 30 °C were flagged as high
  risk, so a `baixo` or `moderado` answer is not a guarantee.
- Caruaru's afternoon values look lower than expected and should be checked against the station.
- It was trained on a single route and a single threshold (30 °C).

## Next steps

- Train a model on the sensor's own readings (inside the cargo box) once real trips are recorded,
  and compare them with the outdoor temperature.
- Use the weather forecast of the day instead of the historical average.
