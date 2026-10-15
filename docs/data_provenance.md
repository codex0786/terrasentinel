# Data provenance and source audit

**Verified for this project** means a smoke test or ingestion has actually run and been recorded
below. Provider documentation alone does not count. Machine-readable status lives in
`configs/data_sources.yaml`.

| Source | Role | Access | Resolution / latency | Project status |
|---|---|---|---|---|
| NASA FIRMS (VIIRS 375 m, MODIS 1 km) | Fire detections, labels | Free MAP_KEY; area CSV API, ≤5 days/request, 5000 transactions / 10 min | NRT around 3 h; SP archive lags by months | smoke-tested and ingested (2024 Mar–May SP); see log below |
| NASA POWER (MERRA-2) | Meteorological context (M2) | No auth; daily regional API, 1 parameter / ≤10°×10° / ≤366 days per request; UTC | 0.5° × 0.625°, daily | 440 files (11 tiles × 4 params × 2015–2024) ingested 2026-10-15; 2,864 points × 3,653 days, 2 missing values; tile-edge duplicates identical |
| GPM IMERG | Rainfall (Workstream B) | Earthdata Login + earthaccess | 0.1°, half-hourly/daily | unverified |
| MODIS MOD13Q1.061 | NDVI/EVI | Earthdata Login + earthaccess | 250 m, 16-day | unverified |
| SMAP | Soil moisture | Earthdata Login + earthaccess | product-dependent | unverified |
| geoBoundaries gbOpen IND ADM1 | State/UT polygons for clipping and regional reporting | No auth; `pipelines/fetch_boundary.py` | 36 units; source DataMeet / Election Commission of India; CC BY 2.5 IN; year represented 2011 (per API, 2026-10-15) | archived 2026-10-15 (sha256 47aa0acb…), 36 units, 0 invalid geometries; units reflect the post-2020 layout despite the 2011 metadata |
| Independent event labels | Non-circular validation | TBD (state forest-fire reports, disaster records) | — | not yet identified |

## Raw archive

- Every response is stored as `data/raw/<provider>/<product>/<sha[:2]>/<sha256>.csv`. The file is
  read-only and never overwritten.
- `data/raw/manifest.jsonl` logs every retrieval: request parameters (never the key), UTC
  retrieval time, size, and checksum. Repeat retrievals that return identical bytes are logged
  but not re-stored.
- Normalisation drops rows only for counted reasons (`ValidationReport`). Row counts must
  reconcile: `in = out + dropped + duplicates`.

## Smoke-test log

| Date | Command | Result |
|---|---|---|
| 2026-10-15 | `python pipelines/smoke_test.py` | PASS: VIIRS_SNPP_NRT 2026-10-12 (687 rows), VIIRS_SNPP_SP 2024-03-15 (8,671 rows); 0 dropped |
| 2026-10-15 | `ingest.py --source VIIRS_SNPP_SP --start 2024-03-01 --end 2024-05-31` | 19 requests OK; re-run was idempotent (identical checksums, nothing re-stored) |
| 2026-10-15 | `audit.py --source VIIRS_SNPP_SP` | 0 invalid rows; 648,130 unique detections; 4 key-collision rows kept; 90 days (03-01..05-29). Re-run 2026-10-15 after fixing order-dependent dedup (FIRMS returned the 05-05 chunk with 2 rows swapped) |
| 2026-10-15 | per-day probe of `VIIRS_SNPP_SP` | **Outage 2024-05-30..06-03 (0 detections/day)**; VIIRS_NOAA20_SP and MODIS_SP normal on the same days. Recorded in `configs/data_sources.yaml` `known_outages` |
| 2026-10-15 | `live_update.py --first 2026-07-01` | 213 one-day NRT files (S-NPP, NOAA-20) for 2026-07-01..10-15; **NRT outage 2026-08-03** (zero India detections for one sensor); 0 of 59,610 rows outside their requested day |
| 2026-10-15 | `data_availability` endpoint | VIIRS_SNPP_SP 2012-01-20..2026-06-30; VIIRS_NOAA20_SP 2018-04-01..2026-06-30; MODIS_SP 2000-11-01..2026-07-31 |

## Citations

- NASA FIRMS. *Fire Information for Resource Management System.* https://firms.modaps.eosdis.nasa.gov
  Cite the specific product DOI (e.g. VNP14IMGTDL_NRT, VNP14IMG) for each source used.
