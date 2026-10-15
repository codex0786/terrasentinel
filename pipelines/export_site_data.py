"""Export the public site's static data (JSON contract v1, see docs/plan_v1.md section 4).

Reads data/live/* (from live_update.py), the frozen model and the boundary, and writes site/public/data/:
meta.json, index.json, days/<date>.json, states.json, states.geojson, results.json.

    python pipelines/export_site_data.py [--out site/public/data]
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from terrasentinel.config import REPO_ROOT, data_dir, load_yaml
from terrasentinel.models.frozen import FrozenLogistic

SCHEMA = "terrasentinel.site.v1"
MODEL = REPO_ROOT / "configs" / "models" / "b1_v0.json"
STALE_HOURS = 30


def band_of(p: np.ndarray, bands: list[dict]) -> np.ndarray:
    out = np.empty(len(p), dtype=object)
    for b in bands:
        out[(p >= b["p_min"]) & (p < b["p_max"] + (1e-9 if b["p_max"] >= 1 else 0))] = b["band"]
    return out


def write_json(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    path.write_text(data)
    return len(data)


def results_block(spec: dict) -> dict:
    """Locked study results and validations (numbers from docs/research_protocol.md and validation reports)."""
    return {
        "study": "Fire persistence v0 (pre-registered; protocol locked at commit e0c9385; 2024 scored once)",
        "primary": {"comparison": "Weather model (M2) vs satellite history (B1)", "metric": "PR-AUC",
                    "difference": 0.0019, "ci95": [-0.0002, 0.0043],
                    "conclusion": "Adding weather gave no robust improvement."},
        "test_2024": [
            {"set": "States used in training", "prevalence": 0.360, "seasonal_B0": 0.651, "B1": 0.683, "M2": 0.685},
            {"set": "Held-out states (Odisha, Haryana, Mizoram)", "prevalence": 0.423, "seasonal_B0": 0.686,
             "B1": 0.724, "M2": 0.724},
        ],
        "b1_vs_seasonal": [{"set": "States used in training", "difference": 0.031, "ci95": [0.020, 0.042]},
                           {"set": "Held-out states", "difference": 0.038, "ci95": [0.016, 0.056]}],
        "bands": spec["band_performance"],
        "validation": [
            {"name": "VIIRS burned area (VNP64A1)", "finding": "Predictions also anticipate mapped burn scars "
             "(lift +0.160 [+0.123, +0.200]); weaker in held-out states (+0.030).", "independence": "partial"},
            {"name": "Uttarakhand Forest Department reports (2026)", "finding": "District totals agree moderately "
             "with satellite detections (Spearman 0.47-0.56), not statistically significant with 13 districts.",
             "independence": "ground-reported"},
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=REPO_ROOT / "site" / "public" / "data")
    args = p.parse_args()
    out: Path = args.out
    live = data_dir() / "live"
    scores = pd.read_parquet(live / "live_scores.parquet")
    det = pd.read_parquet(live / "live_detections.parquet",
                          columns=["latitude", "longitude", "acq_datetime_utc", "frp", "satellite", "region"])
    meta_live = json.loads((live / "live_meta.json").read_text())
    spec = FrozenLogistic.load(MODEL).spec
    bands = spec["bands"]
    scores["band"] = band_of(scores["p_B1"].to_numpy(float), bands)
    scores["day"] = scores["date"].dt.date.astype(str)
    det["day"] = det["acq_datetime_utc"].dt.date.astype(str)

    days = sorted(set(scores["day"]) | set(det["day"]))
    first_scored = meta_live["scored_days"][0]
    days = [d for d in days if d >= first_scored]
    index, state_rows, total = [], [], 0
    for d in days:
        s = scores[scores["day"] == d].sort_values("p_B1", ascending=False)
        dd = det[det["day"] == d]
        final = bool(s["label_final"].all()) if len(s) else d < datetime.now(UTC).date().isoformat()
        cells = [[r.cell_id, round(float(r.lat), 2), round(float(r.lon), 2), r.cell_region,
                  round(float(r.p_B1), 3), r.band, int(r.fire_count_1d), round(float(r.frp_sum_1d), 1),
                  None if pd.isna(r.label) else int(r.label)] for r in s.itertuples()]
        dets = [[round(float(r.latitude), 3), round(float(r.longitude), 3),
                 r.acq_datetime_utc.strftime("%H%M"), round(float(r.frp), 1), str(r.satellite)]
                for r in dd.itertuples()]
        total += write_json(out / "days" / f"{d}.json", {
            "date": d, "outcomes_final": final, "unobserved": d in meta_live["unobserved_days"],
            "cell_fields": ["id", "lat", "lon", "state", "p", "band", "detections_prev_day", "frp_prev_day",
                            "burned_again"],
            "cells": cells,
            "detection_fields": ["lat", "lon", "hhmm_utc", "frp_mw", "satellite"],
            "detections": dets,
        })
        high = s[s["band"] == "high"]
        index.append({"date": d, "detections": len(dd), "cells": len(s), "high": len(high),
                      "outcomes_final": final, "unobserved": d in meta_live["unobserved_days"],
                      "high_burned_again": (float(high["label"].mean()) if final and len(high) else None)})
        for st in sorted(set(s["cell_region"].dropna()) | set(dd["region"].dropna())):
            ss, ds = s[s["cell_region"] == st], dd[dd["region"] == st]
            state_rows.append({"state": st, "date": d, "detections": len(ds), "cells": len(ss),
                               "high": int((ss["band"] == "high").sum())})

    states = {}
    for r in state_rows:
        states.setdefault(r["state"], []).append([r["date"], r["detections"], r["cells"], r["high"]])
    total += write_json(out / "index.json", {"days": index})
    total += write_json(out / "states.json", {"fields": ["date", "detections", "cells", "high"], "states": states})

    region = load_yaml("india.yaml")["region"]
    gdf = gpd.read_file(data_dir() / region["boundary_file"])[["shapeName", "geometry"]]
    gdf["geometry"] = gdf.geometry.simplify(0.01, preserve_topology=True)
    gj = json.loads(gdf.rename(columns={"shapeName": "name"}).to_json(drop_id=True))
    for f in gj["features"]:
        f["geometry"] = _round_geom(f["geometry"], 3)
    total += write_json(out / "states.geojson", gj)
    total += write_json(out / "results.json", results_block(spec))

    now = datetime.now(UTC)
    latest_acq = max(meta_live["latest_acquisition_utc"].values()) if meta_live["latest_acquisition_utc"] else None
    total += write_json(out / "meta.json", {
        "schema": SCHEMA, "generated_at_utc": now.isoformat(timespec="seconds"),
        "pipeline_run_at_utc": meta_live["run_at_utc"],
        "latest_acquisition_utc": meta_live["latest_acquisition_utc"], "data_as_of_utc": latest_acq,
        "stale_after_hours": STALE_HOURS, "latest_day": days[-1] if days else None,
        "model": {"id": spec["model_id"], "sha256": spec["sha256"], "bands": bands,
                  "horizon": spec["horizon"], "trained_on": spec["trained_on"]},
        "sources": ["NASA FIRMS VIIRS NRT (S-NPP, NOAA-20)", "geoBoundaries ADM1 (CC BY 2.5 IN)",
                    "Basemap © OpenStreetMap contributors, OpenFreeMap"],
        "unobserved_days": meta_live["unobserved_days"],
        "disclaimer": "Research prototype. Not an official warning. In an emergency contact local authorities "
                      "(NDMA helpline 1078, State Forest Departments, IMD).",
    })
    print(f"Wrote {len(days)} day files and summaries to {out} ({total / 1e6:.1f} MB total)")


def _round_geom(g: dict, nd: int) -> dict:
    def r(c):
        return [round(c[0], nd), round(c[1], nd)] if isinstance(c[0], float) else [r(x) for x in c]
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


if __name__ == "__main__":
    main()
