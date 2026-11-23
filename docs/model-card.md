# Model card: ColdTrack models

The API serves two small models. Both support a human decision and never trigger an automatic
action, and both answer with a baseline next to the model so the user can compare.

| | Thermal risk (outdoor) | Sensor forecast (cargo) |
|---|---|---|
| Question | Chance that the outdoor air passes 30 °C at a given month and hour | Temperature of the cargo sensor 10 minutes ahead |
| Data | INMET station A307 Petrolina, hourly, 2019–2025 | Readings of the team's own board, stored in the production database (cross-checked with ThingSpeak channel 3515173) |
| Route | `GET /api/predict?mes=&hora=` | `GET /api/predict/sensor?deviceId=` |
| Version | `clima-a307-30c-v1` | `sensor-ridge-10min-v2` |
| Beats its baseline on the test split | Yes (Brier 0.091 vs 0.202) | **No, with the current data** (MAE 0.334 °C vs 0.319 °C) |

---

## 1. Thermal risk model (outdoor, INMET)

### Purpose

Estimates the probability that the outdoor air temperature exceeds 30 °C for a given month and
hour of the day along the Petrolina → Suape route. The dashboard shows it (the mobile app can call
the same route) to help the team choose departure times and decide when to reinforce monitoring
of a refrigerated cargo.

### Model

Climatological model: for each (month, hour) pair, the share of hours above 30 °C in the training
years. A cell with no training hour falls back to the baseline. Code: `analise/explorar.py`
(analysis and evaluation) and `analise/exportar_modelo.py` (export). Report:
`analise/relatorio.md`.

- Version: `clima-a307-30c-v1`.
- Artifact: `cloud/function/modelo_risco.json`, a 12 × 24 probability table plus the number of
  training hours behind each cell, the baseline, the metrics and the risk levels. It is a few
  kilobytes and needs no machine-learning library at runtime.

### Serving

`GET /api/predict?mes=<1..12>&hora=<0..23>` (operator or manager token). It returns the model
probability, the risk level, the baseline probability for comparison, the training hours behind
the cell, the model version and both Brier scores. Details: `docs/api.md` and the OpenAPI
specification (`/api/openapi.json`).

Risk levels: `baixo` (low) up to 0.20, `moderado` (moderate) up to 0.50, `alto` (high) above
0.50. The 0.50 cut is the same one used to measure accuracy below.

### Data

- Source: INMET automatic stations, hourly data, 2019–2025 (A307 Petrolina as the main station).
- Hours without a valid reading were discarded, never filled.
- Training: 2019–2022 (22,875 hours). Test: 2023–2025 (9,278 hours). The split is temporal, so the
  model is evaluated on years it has not seen. The served table is the one trained on 2019–2022,
  the same one that was evaluated.

### Evaluation (test years)

| Metric | Value |
|---|---|
| Brier score, model | 0.091 |
| Brier score, naive baseline (overall share of hours above 30 °C in training, 0.214) | 0.202 |
| Error reduction over the baseline | 55% |
| Accuracy when flagging "risk hour" (probability ≥ 50%) | 87% |
| Share of hours above 30 °C that the model flagged | 62% |

### Limitations

- **It does not use the readings of the project's own sensor.** It estimates the outdoor
  temperature at the origin, not the temperature inside the cargo box, and not the conditions
  along the rest of the route.
- It describes the typical pattern, not the weather forecast of the day.
- Public stations have long gaps (for example, Petrolina has no valid hours in 2025), so some
  months are estimated from fewer years. `horasDeHistorico` in the answer shows the sample
  size of each cell.
- It misses part of the hot hours: only 62% of the test hours above 30 °C were flagged as high
  risk, so a `baixo` or `moderado` answer is not a guarantee.
- Caruaru's afternoon values look lower than expected and should be checked against the station.
- It was trained on a single route and a single threshold (30 °C).

---

## 2. Sensor forecast model (cargo sensor, 10 minutes ahead)

### Purpose

Estimates the temperature that the cargo sensor will read 10 minutes from its last reading, and
the status that temperature would have in the cargo profile (`NORMAL`, `ATENCAO`, `CRITICO`). The
goal is to warn before the reading leaves the range (thermal excursion), so the operator or the
driver can check the door, the refrigeration unit or the route in time.

Why a short-term forecast and not anomaly detection: the real base has no labelled fault (no
stuck sensor, no door opening, no refrigeration failure), so an anomaly detector could only be
scored on faults injected by hand. A forecast can be scored on the real readings themselves,
with a temporal split and an honest baseline.

### Model

- Baseline: **persistence** (the temperature in 10 minutes equals the last reading).
- Model: **ridge regression without intercept** on the change `target − last reading`, with three
  features computed from the last 10 minutes of the same continuous stretch of readings:
  `d5` (last reading minus the reading 5 minutes before), `d10` (same for 10 minutes) and `m10`
  (mean of the last 10 one-minute values minus the last reading). Fixed `lambda = 1`. No intercept
  because a constant drift learned on a few hours would not hold on other days.
- The value at a given minute is the last reading at or before that minute. A gap of more than
  5 minutes between readings starts a new stretch; no sample crosses a gap.
- Code: `analise/sensor/modelo_previsao.py` (cleaning, samples, split, training, evaluation,
  export). The feature function is `cloud/function/previsao_sensor.atributos`, the same one the
  route uses, so training and serving compute the features identically. Report:
  `analise/sensor/relatorio_previsao.md`.
- Version: `sensor-ridge-10min-v2` (retrained on 2026-11-23 with the 2026-11-17 to 11-20 collection). Artifact: `cloud/function/modelo_sensor.json` (three
  coefficients, the window, the gap limit, the training and test periods and the metrics). No
  numpy or scikit-learn at runtime.

### Data

- Source: the readings the team's ESP32-C3 board with a DHT11 sent to the API, read from the
  production database (the same data the route receives when serving): 12,015 readings
  carrying the firmware sequence number, from 2026-11-17 02:33 to 2026-11-20 08:10 UTC, exported with
  `infra/backup/exportar.py` and converted by `analise/sensor/descrever_cosmos.py --converter`.
  Readings without a sequence number are left out: the database does not store the reading origin
  and it received demonstration data before the board went live. The
  public ThingSpeak channel 3515173 (12,730 readings, same board) is used as a cross-check.
- Cleaning: readings without temperature or timestamp, outside the DHT11 physical range (0 to
  50 °C) or with a repeated timestamp are dropped (none were dropped in the current base).
- Samples: one per minute inside continuous stretches, with 10 minutes of history and the target
  10 minutes later in the same stretch: 4,211 samples (about 70 h) from 5 stretches.
- Temporal split: the most recent 30% of the sample instants are the test set
  (2026-11-19 05:07 to 2026-11-20 08:00 UTC, 1,267 samples); the training set (2026-11-17 to
  2026-11-19 04:56 UTC, 2,944 samples) only keeps samples whose target is before the first test instant, so no
  future value leaks into training. The served coefficients are the ones trained on this
  training set, the same ones that were evaluated.

### Evaluation (test split)

| Metric (°C) | Model (ridge) | Baseline (persistence) |
|---|---|---|
| MAE (primary metric, chosen before training) | 0.334 | 0.319 |
| RMSE | 0.662 | 0.652 |

**The model does not beat the baseline on either metric.** With the 48-hour collection the test
set grew from 218 to 1,267 samples and the result is now consistent: persistence also wins with
other test fractions (20% and 40%, reported in `relatorio_previsao.md` for information only) and
on the ThingSpeak cross-check (MAE 0.346 vs 0.311 °C). Other attempts on 2026-11-23 outside the
pipeline (median/LAD regression, gradient boosting with absolute-error loss, a 30-minute window
with more features, hour of day) did not beat persistence either: the median regression collapses
into it (MAE 0.3191 vs 0.3190 °C) and boosting stayed above it (0.334 to 0.341 °C vs 0.318 °C).
The series only moves in DHT11 resolution steps, and with no real excursion in the base there is
no signal to learn. Because of that, the exported file has `superaBaseline: false` and the route answers `recomendada:
"baseline"`: the screen should show the persistence value, and `antecipaExcursao` stays `false`
(a repeated reading cannot anticipate anything). The model value is still returned so the
comparison stays visible.

### Serving

`GET /api/predict/sensor?deviceId=<id>` (operator or manager; the sensor must belong to the
company of the token, otherwise 404) or `GET /api/predict/sensor` with a driver token (always the
sensor of the vehicle linked to the driver). The route reads the last 20 minutes of the sensor
from the database and returns the last reading, the model forecast, the baseline, which one is
recommended, whether the recommended forecast anticipates a worse status, the reason when there
is no forecast (`sem_leituras`, `sem_leitura_recente` when the last reading is older than
5 minutes, `historico_insuficiente` when there are less than 10 continuous minutes), and the model
version with both test errors. Details: `docs/api.md` and the OpenAPI specification.

### Limitations

- **Limited data**: about 70 hours of samples, in 5 stretches separated by gaps (the longest
  continuous stretch is about 14 h); the test set spans about 27 h.
- **Bench, not a refrigerated box**: the board sits indoors (readings between 21 and 37 °C). There is no real thermal
  excursion in the base (door opening, refrigeration failure), which is exactly the event the
  model should anticipate. The series is almost flat and moves in DHT11 resolution steps, a
  setting where persistence is very hard to beat.
- The model only extrapolates the sensor's own series: it knows nothing about the outdoor
  weather, the route or the door.

### Retraining

When a new collection (or a real trip) is available, export the database, convert it with
`descrever_cosmos.py --converter` and retrain with `python modelo_previsao.py`; the ThingSpeak command below only
refreshes the cross-check. It downloads the
channel again, retrains, re-evaluates against persistence and exports the new file:

```bash
cd analise/sensor
python modelo_previsao.py --baixar
```

If the new test shows a lower MAE than persistence, `superaBaseline` becomes `true` and the route
starts recommending the model with no code change; the API is published with the new
`modelo_sensor.json`.

---

## Next steps

- Retrain the sensor forecast above all with readings from a real refrigerated box, where excursions exist.
- Cross the sensor readings with the outdoor temperature (model 1) to explain the excursions.
- Use the weather forecast of the day instead of the historical average in model 1.
