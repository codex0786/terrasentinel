# Research protocol: Workstream B v0, rainfall anomalies vs reported heavy-rain/flood days

Status: **DRAFT.** Design choices were agreed with the project owner on 2026-10-15, before any rainfall-event
comparison. This file will be marked LOCKED (same rule as the fire protocol) before the 2021–2023 test period
is scored.

## Question

Does IMERG satellite rainfall, expressed as local anomalies, identify **state-days with an IMD-reported
heavy-rain or flood event** better than (B0) the state's seasonal event climatology and (B1) raw rainfall
amounts?

This is **same-day detection / characterization**, not forecasting. Satellite rainfall alone cannot establish
inundation: the label is a *reported impact* of heavy rain.

## Data

- **Rainfall:** GPM IMERG Final daily v07, India window, native 0.1° grid (identical to the project grid).
- **Events:** IFI-Impacts v3 (Zenodo 10.5281/zenodo.11275211, CC-BY-4.0). All 2001+ events are sourced from IMD.
- **States:** geoBoundaries ADM1 (36 units). A cell belongs to the state containing its centre. Units with
  fewer than 10 cells (≈1,200 km²) are excluded: Chandigarh, Puducherry, Lakshadweep, and similar.

## Label (state s, UTC day D)

1 if ≥1 IFI event with `Main Cause` matching `rain|flood|cloudburst` (case-insensitive) is active on D
(start ≤ D ≤ end) and lists state s; otherwise 0. Multi-state events count for each listed state. Events
lasting more than 30 days are excluded as non-specific (counted and reported). State names are mapped with
`configs/rainfall_state_aliases.yaml`.

A label of 0 means *no reported event*, not *no flooding*.

## Features (may use D, D−1, D−2, because this is detection on day D)

Over the state's cells:
- mean daily rain on D; mean 3-day total (D−2..D);
- fraction of cells whose day-D rain exceeds the cell's **99th percentile** of daily rain;
- fraction of cells whose 3-day total exceeds the cell's 99th percentile of 3-day totals;
- maximum cell 3-day total.

Percentiles are per cell and calendar month, pooling months m−1, m and m+1, from **2001–2014 only**. That
period ends before every label year.

## Periods

Climatology 2001–2014 · train 2015–2019 · validation 2020 · **test 2021–2023** (IFI ends in 2023). 7-day embargo
at each boundary.

## Models

| Level | Model | Inputs |
|---|---|---|
| B0 | Seasonal climatology | P(event \| state, calendar month) from training years (add-one smoothing) |
| B1 | Raw rain (logistic) | log1p(mean 1-day), log1p(mean 3-day) |
| M1 | Anomaly model (logistic) | B1 + exceedance fractions (1-day, 3-day) + log1p(max cell 3-day) + logit(B0 rate) |

## Evaluation

- **Reporting changes ~8× from 2021** (IFI: about 70–180 events/yr before, 338 / 1,138 / 634 in 2021–23). The primary
  metric is therefore rank-based.
- **Primary endpoint:** ROC-AUC difference **M1 − B0** on the pooled 2021–2023 test set, 95% block-bootstrap
  CI over (state × ISO week), 2,000 resamples, seed 20261015.
- **Minimum worthwhile improvement:** +0.02 ROC-AUC.
- **Secondary:** M1 − B1 and B1 − B0 (ROC-AUC); PR-AUC with prevalence **per test year**; results by state.
- **Decision rule:** the same four-way rule as the fire protocol (robust and worthwhile / robust but small /
  no robust improvement / robustly worse).
- Models are fit once on train; the test is scored once.

## Known limitations

- Labels come from IMD reports, so their density depends on reporting practice and media attention.
- IMD's "heavy rain" events are partly defined from rain gauges: independent of satellite rainfall, but not of
  rainfall itself.
- A state-level unit is coarse; one large state can contain both flooded and dry areas on the same day.

## Change log

| Date | Change |
|---|---|
| 2026-10-15 | Draft agreed (state × day, same-day detection, ROC-AUC primary); pushed publicly before any rainfall result. |
| 2026-10-15 | Data audit: IMERG 2001–2024 complete (8,766 days, 0 missing). Seven daily maxima above 1,000 mm all fall over sea (cyclones). Dataset: 105,184 state-days in 32 states (3 units with fewer than 10 cells excluded), 2,566 positives; 132 events over 30 days excluded; 0 unmatched state names. |
| 2026-10-15 | Development run, validation 2020 only: ROC-AUC B0 0.804, B1 0.713, M1 0.857; M1 − B0 +0.053 [+0.021, +0.089]. PR-AUC M1 0.066 vs B0 0.065 (prevalence 0.017). **Deviation:** the report showed label counts for the 7-day embargo rows (3 events), part of which border the test period. Those counts are now withheld as well. No test-period rows were scored. Nothing was changed in response. |
