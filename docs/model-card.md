# Model card: thermal risk model (preliminary)

## Purpose

Estimates the probability that the outdoor air temperature exceeds 30 °C for a given month and
hour of the day along the Petrolina → Suape route. The dashboard is expected to use it to help
the team choose departure times and decide when to reinforce monitoring of a refrigerated cargo.
It supports a human decision; it does not trigger any automatic action.

## Model

Climatological model: for each (month, hour) pair, the share of hours above 30 °C in the training
years. Code: `analise/explorar.py`. Report: `analise/relatorio.md`.

## Data

- Source: INMET automatic stations, hourly data, 2019–2025 (A307 Petrolina as the main station).
- Hours without a valid reading were discarded, never filled.
- Training: 2019–2022 (22,875 hours). Test: 2023–2025 (9,278 hours). The split is temporal, so the
  model is evaluated on years it has not seen.

## Evaluation (test years)

| Metric | Value |
|---|---|
| Brier score, model | 0.091 |
| Brier score, naive baseline (overall mean probability) | 0.202 |
| Error reduction over the baseline | 55% |
| Accuracy when flagging "risk hour" (probability ≥ 50%) | 87% |
| Share of hours above 30 °C that the model flagged | 62% |

## Limitations

- It describes the typical pattern, not the weather forecast of the day.
- It models outdoor temperature, not the temperature inside the cargo box. It has not yet been
  combined with the readings of the project's own sensor.
- Public stations have long gaps (for example, Petrolina has no valid hours in 2025), so some
  months are estimated from fewer years.
- Caruaru's afternoon values look lower than expected and should be checked against the station.
- It was trained on a single route and a single threshold (30 °C).

## Next steps

Serve the estimate through an API route (`/predict`), show it on the dashboard, and compare the
sensor's own readings with the outdoor temperature on real trips.
