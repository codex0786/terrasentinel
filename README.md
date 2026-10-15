# TerraSentinel

Open-source, research-grade Earth-observation hazard intelligence for India. It aims to turn
free satellite observations into **validated, uncertainty-aware** environmental intelligence.
It separates observations from predictions and reports what remains unknown.

> **Status (2026-10-15): v0 study complete.** The protocol was locked (commit `e0c9385`) and the 2024
> test year was scored once. **Pre-registered result: adding NASA POWER weather (M2) gave no robust
> improvement over satellite fire history alone (B1)**: PR-AUC +0.0019 [95% CI −0.0002, +0.0043], below
> the +0.01 threshold. Satellite history robustly beat the seasonal baseline, including in held-out states.

### Locked test results (2024; scored once)

PR-AUC, with 95% block-bootstrap CIs (state × ISO week) for differences:

| Test set | Prevalence | B0 seasonal | B1 satellite-only | M2 + weather | M2 − B1 (primary) | B1 − B0 |
|---|---|---|---|---|---|---|
| Training states | 0.360 | 0.651 | 0.683 | 0.685 | +0.002 [−0.000, +0.004] | +0.031 [+0.020, +0.042] |
| Held-out states (Odisha, Haryāna, Mizoram) | 0.423 | 0.686 | 0.724 | 0.724 | +0.001 [−0.003, +0.005] | +0.038 [+0.016, +0.056] |

Full details, secondary endpoints, and interpretation limits: [research protocol](docs/research_protocol.md#results-on-the-locked-test-period-scored-once-2026-10-15-protocol-commit-e0c9385).
Labels are next-day satellite *detections*, not verified fire. See [limitations](docs/limitations.md).

## What exists today

| Component | Location | State |
|---|---|---|
| FIRMS area-API client (chunking, retries, rate limit, key redaction, request budget) | `src/terrasentinel/ingestion/firms.py` | tested offline |
| Immutable checksummed raw archive + retrieval manifest | `src/terrasentinel/ingestion/archive.py` | tested |
| FIRMS schema validation / normalisation with row reconciliation | `src/terrasentinel/validation/firms_schema.py` | tested on fixture |
| 0.1° analysis grid | `src/terrasentinel/geospatial/grid.py` | tested |
| Trailing-window features with an availability-time cutoff | `src/terrasentinel/features/trailing.py` | leakage-tested |
| Fire-persistence labels | `src/terrasentinel/labels/persistence.py` | tested |
| Temporal split with embargo + geographic holdout | `src/terrasentinel/evaluation/splits.py` | tested |
| India boundary clipping and cell-to-state mapping | `src/terrasentinel/geospatial/boundary.py` | tested on synthetic polygons |
| Baselines B-null, B0 seasonal, B1 satellite-only | `src/terrasentinel/models/baselines.py` | leakage- and synthetic-tested |
| PR-AUC, ROC-AUC, Brier, ECE, alert budget, block bootstrap | `src/terrasentinel/evaluation/metrics.py` | tested |
| Pipelines: ingest, smoke test, audit, fetch boundary, build dataset, train baselines | `pipelines/` | run end-to-end on synthetic data |

Read first: [research protocol](docs/research_protocol.md), [data provenance](docs/data_provenance.md),
and [limitations](docs/limitations.md).

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,geo,earthdata]'
cp .env.example .env   # then add FIRMS_MAP_KEY (free: https://firms.modaps.eosdis.nasa.gov/api/map_key/)
.venv/bin/python -m pytest
```

## First real-data steps

```bash
.venv/bin/python pipelines/smoke_test.py
.venv/bin/python pipelines/ingest.py --source VIIRS_SNPP_SP --start 2024-03-01 --end 2024-05-31
.venv/bin/python pipelines/audit.py
.venv/bin/python pipelines/fetch_boundary.py        # then set boundary_file in configs/india.yaml
# configs/experiments/fire_persistence_v0.yaml is already filled in for the v0 study:
.venv/bin/python pipelines/build_dataset.py --experiment configs/experiments/fire_persistence_v0.yaml
.venv/bin/python pipelines/train_baselines.py --experiment configs/experiments/fire_persistence_v0.yaml
```

Record each smoke-test result in `docs/data_provenance.md`. Fix the split dates in the protocol
**before** fitting any model.

## Live near-real-time mode

```bash
.venv/bin/python pipelines/live_update.py            # daily: fetch FIRMS NRT, score today with locked B1
.venv/bin/python pipelines/evaluate_nrt.py           # B1 on final NRT days vs the same 2024 SP window
```

Each run re-fetches the last 3 days because NRT files keep filling in; every version is archived. The dashboard's
**Live** mode shows today's predictions, data freshness, a stale-data warning after 30 h, and "pending" outcomes
until each day has ended.

Post-lock NRT check (not pre-registered), 2026-08-01..10-14 vs 2024-08-01..10-14 SP: B1 PR-AUC 0.749 vs 0.664 at
similar prevalence (0.334 vs 0.328). The two archives do not overlap, so product, lag and year differences cannot be
separated.

## Burned-area validation (secondary, pre-specified)

Checked against VIIRS burned area (VNP64A1, burn scars from surface reflectance), the locked B1 predictions show
lift over prevalence on 2024 test cells: PR-AUC 0.233 vs a prevalence of 0.074, CI [+0.123, +0.200]. The lift is
smaller in held-out states (+0.030 [+0.006, +0.057]). Weather (M2) slightly *reduced* agreement. The two labels
agree weakly (κ ≈ 0.1), because burned-area mapping misses many small fires. See
[validation_burned_area.md](docs/validation_burned_area.md).

## Dashboard (research prototype)

```bash
.venv/bin/pip install -e '.[dashboard]'
.venv/bin/python pipelines/score.py --experiment configs/experiments/fire_persistence_v0.yaml
.venv/bin/streamlit run app/dashboard/app.py --server.port 8502
```

For any UTC day from 2020 to 2024 it shows observed VIIRS detections (orange) and next-day persistence
predictions (blue circles, red outline = top 10% flagged). It labels whether the day is in-sample, validation
or locked test. Outcomes stay hidden until you reveal them, and outage days show no predictions. It is
not an emergency warning service.

## Principles

- Raw data are immutable. Derived data are reproducible from the manifest and config.
- Every feature obeys `available_at < cutoff`. `tests/leakage/` enforces this, and a deliberately
  planted leak was confirmed to fail those tests.
- Baselines come first. More complex models must beat them on a pre-registered metric with CIs.
- Credentials live only in the environment.
