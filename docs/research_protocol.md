# Research protocol: Workstream A, fire persistence

Status: **DRAFT, not locked.** Items marked **TBD** must be decided and committed *before*
the final test period is opened. The commit hash that locks this file is the pre-registration.

## Hypothesis

For the outcome defined below, adding meteorological context to satellite-only features gives
better out-of-time precision–recall performance than (0) a seasonal-persistence baseline and
(1) a satellite-only model.

This is a hypothesis, not a result. Null and negative results will be reported.

## Data and periods (agreed 2026-10-15, before any model was fit)

- **Sensors:** VIIRS S-NPP SP and VIIRS NOAA-20 SP. Labels and features pool qualifying detections from
  both; both cover all of 2020–2024.
- **Label days:** 2020-01-01 to 2024-12-31. A day is excluded if *either* sensor has no observations
  (zero detections in India, or a listed outage), so a label of 0 always means the same sensor set.
- **Splits:** train 2020–2022, validation 2023, test 2024, with a 7-day embargo at each boundary.
- **B0 history:** S-NPP only, 2015–2019 onward (5 prior years per row). NOAA-20 starts 2018-04, so
  mixing it in would make the seasonal score drift with sensor availability.
- **Study area:** India, geoBoundaries ADM1 (see data_provenance.md). Detections outside it are dropped.
- **Geographic holdout:** Odisha, Haryāna, Mizoram (eastern forest; crop residue, with Punjab kept in
  training; NE shifting cultivation). About 11.7% of training-period rows. These states never enter training.
- **Alert budget:** primary = top 10% of each day's eligible cells; secondary = fixed 100/day. The daily
  population ranges from a median of ~50–85 in Jul–Sep to ~2,200 in March, so a fixed budget saturates
  in the monsoon.
- Holdout and budget were chosen from training-period population counts only; no model had been fit.
- **Still open (must be fixed before the lock):** minimum worthwhile improvement on the primary metric.

## Unit of analysis

Primary: **grid cell × UTC day** on a regular 0.1° lat/lon grid anchored at (6°N, 68°E)
(`configs/india.yaml`). Secondary: clustered fire events (definition TBD, M4).

## Outcome (implemented in `src/terrasentinel/labels/persistence.py`)

- **Population for day D:** cells with ≥1 qualifying detection *acquired* on UTC day D−1 and
  *available* before the D cutoff (D 00:00 UTC). This makes eligibility knowable at prediction time.
- **Label:** 1 if ≥1 qualifying detection is acquired in the cell on UTC day D, else 0.
- **Qualifying detection:** VIIRS confidence ∈ {nominal, high}; MODIS confidence ≥ 30.
- Label 0 means *no detection*, not *confirmed absence of fire*.

This is persistence prediction (next-day continuation). It is **not** ignition forecasting.

## Prediction-time rule (implemented in `src/terrasentinel/features/trailing.py`)

A feature for row (cell, D) may use an observation only if `available_at < D 00:00 UTC`,
where `available_at = acquisition time + source latency`. Every window is trailing,
`[cutoff − w, cutoff)`. No centred windows, no full-period normalisation.
Science-quality (SP) experiments assume latency 0. This is a documented simplification
because SP data did not exist in real time. A separate NRT evaluation uses measured latency.

## Model ladder

| Level | Model | Features |
|---|---|---|
| B-null | Training prevalence | none (reference: PR-AUC = prevalence) |
| B0 | Seasonal persistence, Platt-scaled | fraction of days with detection in the same cell, ±15 d around the same day-of-year, previous 5 years. Years before the archive start are skipped, not counted as zero |
| B1 | Satellite-only (L2 logistic regression on log1p, standardised) | trailing counts 1/3/7/30 d, FRP sums 1/7 d, days since last detection |
| M2 | Meteorology-augmented (same learner as B1) | B1 + NASA POWER trailing weather anomalies |
| M3 | Gradient-boosted trees (conditional) | only if M2 leaves a meaningful gap; same feature sets |

Implemented in `src/terrasentinel/models/baselines.py`; run via `pipelines/train_baselines.py`.
B1 coefficients are reported but not interpreted causally, since the count windows are collinear.

## Evaluation

- **Primary metric (proposed):** PR-AUC on the temporal test period, with M2 − B1 difference
  and 95% CI from a **block bootstrap over (state × week) blocks**. Final choice: **TBD at lock.**
- **Secondary metrics:** precision/recall at a fixed alert budget (top-k cell-days per day),
  Brier score, reliability diagram, ROC-AUC.
- **Splits:** temporal train/val/test with an embargo gap (`src/terrasentinel/evaluation/splits.py`).
  Cutoff dates: fixed above (train ≤ 2022-12-31, val ≤ 2023-12-31, test 2024).
  Geographic holdout: fixed above. Held-out states are scored as `geo_val` during development and
  as `geo_test` after the lock.
- **Alert budget:** fixed above. Reports flag `fixed100_saturated` when the fixed budget flags most rows.
- **Test-set guard:** `train_baselines.py --evaluate-test` refuses to run until this file
  starts with `Status: **LOCKED**`.
- **Minimum worthwhile improvement:** **TBD after the audit**, based on prevalence.
- Thresholds are chosen on validation data only.

## Acceptance

M2 is said to improve on B1 only if the CI for the primary-metric difference excludes 0 on the
locked test period. Otherwise the conclusion is: no robust improvement under the tested conditions.

## Change log

| Date | Change |
|---|---|
| 2026-10-15 | Initial draft; outcome, cutoff rule, and leakage tests implemented. |
| 2026-10-15 | Boundary clipping, B-null/B0/B1, metrics, block bootstrap, and test-set lock implemented. Checked on synthetic data only. |
| 2026-10-15 | Periods, sensors, and the outage rule fixed (see "Data and periods"). B0 history restricted to S-NPP. No model had been fit on real data. |
| 2026-10-15 | Holdout states and alert budget fixed. `configs/experiments/fire_persistence_v0.yaml` sha256 prefix `32864af15e6310f2` frozen before the first model fit. |
| 2026-10-15 | First development run (train → val/geo_val). **Deviation:** that run's report showed test-period row counts *and label prevalence* (test 0.360, geo_test 0.423). No test predictions or model metrics were computed. The report now withholds test label statistics until the lock. Nothing was changed in response to the values. |
