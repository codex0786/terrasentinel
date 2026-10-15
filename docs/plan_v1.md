# TerraSentinel v1 plan: gaps, improvements, public frontend, GitHub deployment

Written 2026-10-15. Decisions agreed with the project owner:
- audience: **public and decision-makers** (plain language first, research detail one click away);
- stack: **React + MapLibre**;
- deployment: **GitHub only, no Docker** (GitHub Pages for the site, GitHub Actions for the daily data job).

## 1. Where things stand

| Area | State |
|---|---|
| Fire study v0 | Complete. Locked test 2024; weather gave no robust gain; B1 robustly beats seasonal B0 |
| Validation | Burned area: supporting; Uttarakhand ground reports: moderate, not significant |
| Live mode | Works locally, run by hand; needs the study's training data to refit B1 each run |
| Dashboard | Streamlit, local only; built for researchers, not the public |
| Rainfall v0 | Protocol drafted (public), pipeline built and tested; IMERG download in progress |
| Vegetation (C) | Not started |
| Deployment | None |

## 2. Gaps and improvements, in priority order

1. **Freeze the deployed model.** Live scoring currently refits B1 from 1.6 M local rows. Export the fitted B1
   (imputer medians, scaler, coefficients) to a small versioned JSON. Score with numpy and test that the output
   equals sklearn's. Live scoring then needs no training data. *(Required for deployment.)*
2. **Automate the daily update.** A scheduled GitHub Action: fetch FIRMS NRT (36 days) → features → frozen B1 →
   export JSON → build site → deploy to Pages. The FIRMS key is a repository secret. *(Required.)*
3. **Public frontend** (section 3). *(Required.)*
4. **Data contract and freshness.** Versioned JSON schema, a `meta.json` with data-as-of times, a stale-data
   banner, and a failure state if the daily job breaks. Contract tests in CI.
5. **Plain-language probability.** Show risk bands (low/medium/high, from validated precision per band) rather
   than raw percentages, with "how often were we right?" on hover.
6. **CI hygiene.** Update actions off Node 20 (deprecation warning); add frontend build and type checks to CI.
7. **Finish rainfall v0:** development run → lock → single test run. Then a rainfall layer in the frontend.
8. **Later:** NOAA-21 as a third sensor; event-level evaluation; vegetation workstream; Hindi UI; accessibility audit.

## 3. Frontend design (public and decision-makers)

**Pages / views**
- **Today (home):** an India map with fires detected in the last 24 h (orange) and "likely to continue tomorrow"
  areas (blue, high band outlined). A header shows "Data as of 15 Oct, 21:55 UTC · next update ~06:30 UTC"; a
  stale banner appears after 30 h. A side panel (sheet on mobile) has national counts and a top-states list.
- **State view:** pick a state from the list or the map. Shows today's counts, high-likelihood areas, and a 30-day
  trend of detections and predictions.
- **Area detail (click a cell):** a plain-language card: "Fire was detected here yesterday (6 detections). There
  is a *high* chance it is still burning tomorrow. In past tests, 8 of 10 areas we marked high did burn
  again." Plus the satellite, time, and raw numbers under "details".
- **Past days:** a date picker over the last 30 days of NRT data. Outcomes ("did it burn again?") are shown for
  completed days.
- **How it works:** method in plain words; the locked results; validation; limitations; data sources and citations.
- **Always visible:** "Not an official warning. For emergencies contact NDMA (1078), State Forest Departments,
  IMD." with links.

**Design principles:** mobile-first; colour-blind-safe palette (orange observations vs blue predictions, never
red/green for meaning); light and dark mode; keyboard accessible; text at least 14 px; load under 2 s on 4G
(gzipped JSON under 300 KB for "today").

**Tech:** Vite + React + TypeScript; MapLibre GL with OpenFreeMap vector tiles (free, no key, OSM attribution);
hash routing (works on Pages); no UI framework; CSS variables; charts as small inline SVG.

## 4. Data contract (static JSON under `site/public/data/`)

| File | Content |
|---|---|
| `meta.json` | schema version, generated_at, latest acquisition per sensor, model id and hash, outage days, freshness |
| `days/YYYY-MM-DD.json` | per day: predicted cells `[id, lat, lon, state, p, band, n_prev, frp_prev, outcome or null]` and detections `[lat, lon, hhmm, frp, sat]` |
| `index.json` | list of available days with national counts |
| `states.json` | per state × day: detections, cells predicted, high-band cells |
| `states.geojson` | simplified state outlines (about 300 KB) |
| `results.json` | locked study results and validation summaries (static) |

## 5. Deployment (GitHub only)

- `.github/workflows/pages.yml`: triggered on a daily schedule (06:30 UTC), manually, and on push to `main`.
  Steps: Python setup → `pip install -e .[geo]` → fetch boundary (cached) → `live_update.py --frozen-model` →
  `export_site_data.py` → `npm ci && npm run build` → `actions/deploy-pages`.
- Owner one-time setup: add the `FIRMS_MAP_KEY` repository secret and enable Pages (source: GitHub Actions).
- If the data job fails, the previous site stays up and its banner shows the data age.

## 6. Execution order

1. Frozen model + tests → 2. export script + JSON contract + tests → 3. frontend scaffold and Today view →
4. state view, area card, past days, How it works → 5. Pages workflow → 6. owner adds the secret and enables Pages →
first deploy → 7. finish rainfall v0 → rainfall layer.
