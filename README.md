# TerraSentinel

Open-source, research-grade Earth-observation hazard intelligence for India. It aims to turn
free satellite observations into **validated, uncertainty-aware** environmental intelligence.
It separates observations from predictions and reports what remains unknown.

> **Status (2026-10-15): baselines and the meteorology model (M2) evaluated on validation; test not yet scored.**
> VIIRS S-NPP (2015–2024) and NOAA-20 (2019–2024) detections and NASA POWER weather (2015–2024) are
> ingested and audited; the fire-persistence dataset (1.6 M cell-days in India) is built. The pre-registered
> comparison (M2 vs B1 on the locked 2024 test year) has **not** been run. Validation numbers are
> development results, not findings.

### Development results (validation 2023, not the locked test)

PR-AUC, with 95% block-bootstrap CIs (region × ISO week) for model differences:

| Eval set | Prevalence | B-null | B0 seasonal | B1 satellite-only | M2 + weather | B1 − B0 | M2 − B1 |
|---|---|---|---|---|---|---|---|
| Training states | 0.367 | 0.368 | 0.690 | 0.713 | 0.718 | +0.023 [+0.012, +0.034] | +0.005 [+0.003, +0.007] |
| Held-out states (Odisha, Haryāna, Mizoram) | 0.463 | 0.463 | 0.703 | 0.758 | 0.762 | +0.055 [+0.031, +0.075] | +0.004 [−0.000, +0.008] |

Weather improves calibration (ECE 0.017 → 0.013) but leaves precision at a 10%-per-day alert budget unchanged.

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
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,geo]'
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

## Principles

- Raw data are immutable. Derived data are reproducible from the manifest and config.
- Every feature obeys `available_at < cutoff`. `tests/leakage/` enforces this, and a deliberately
  planted leak was confirmed to fail those tests.
- Baselines come first. More complex models must beat them on a pre-registered metric with CIs.
- Credentials live only in the environment.
