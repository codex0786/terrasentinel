"""Daily near-real-time update: fetch FIRMS NRT, rebuild recent features, score with the locked model.

    python pipelines/live_update.py                      # normal daily run (last ~5 weeks)
    python pipelines/live_update.py --first 2026-07-01   # backfill the whole NRT archive window

Writes data/live/live_scores.parquet and data/live/live_meta.json.
The model is the frozen locked B1 (configs/models/b1_v0.json, fit on the study's 2020-2022 training rows and
verified equal to the study scores). It is applied to NRT data unchanged and needs no training data.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from terrasentinel.config import REPO_ROOT, data_dir, load_dotenv, load_yaml, require_env
from terrasentinel.experiments.fire_persistence import prepare_detections
from terrasentinel.features.trailing import build_trailing_features
from terrasentinel.geospatial.boundary import cell_regions, load_boundary
from terrasentinel.geospatial.grid import Grid
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.ingestion.firms import BBox, FirmsClient
from terrasentinel.labels.persistence import build_persistence_rows, find_unobserved_days
from terrasentinel.live.nrt import NRT_SOURCES, fetch_nrt, label_final, load_nrt
from terrasentinel.models.frozen import FrozenLogistic

MODEL = REPO_ROOT / "configs" / "models" / "b1_v0.json"
HISTORY_DAYS = 31   # features need 30 days of trailing history before the first scored day


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--first", type=date.fromisoformat,
                   help="first day to fetch (default: enough history for --scored-days scored days)")
    p.add_argument("--scored-days", type=int, default=30, help="days to score when --first is not given")
    p.add_argument("--refresh-days", type=int, default=3, help="always re-fetch this many most recent days")
    p.add_argument("--no-fetch", action="store_true", help="rebuild from the archive without downloading")
    args = p.parse_args()

    now = datetime.now(UTC)
    today = now.date()
    first = args.first or today - timedelta(days=HISTORY_DAYS + args.scored_days - 1)
    india = load_yaml("india.yaml")
    region = india["region"]
    feats = load_yaml("features.yaml")
    lag = feats["prediction"]["availability_lag_hours"]["nrt"]
    bbox = BBox(**region["bbox"])
    archive = RawArchive(data_dir() / "raw")

    if not args.no_fetch:
        load_dotenv()
        client = FirmsClient(require_env("FIRMS_MAP_KEY"), archive)
        recs = fetch_nrt(client, bbox, first, today, args.refresh_days, today)
        print(f"Fetched {len(recs)} NRT day-file(s); {sum(r.newly_written for r in recs)} new or revised", flush=True)

    raw, inventory = load_nrt(archive, first, today, bbox=bbox)
    grid = Grid.from_config(india)
    boundary = load_boundary(data_dir() / region["boundary_file"], region["boundary_name_field"])
    det, info = prepare_detections(raw, grid, boundary, region["bbox"], lag)

    start = first + timedelta(days=HISTORY_DAYS)
    unobserved = pd.DatetimeIndex([], tz="UTC")
    for src in NRT_SOURCES:   # today is still filling in, so only completed days are checked for outages
        unobserved = unobserved.union(find_unobserved_days(det[det["source"] == src], start.isoformat(),
                                                           (today - timedelta(days=1)).isoformat()))
    rows = build_persistence_rows(det, start.isoformat(), today.isoformat(), unobserved)
    rows = build_trailing_features(det, rows, feats["features"]["trailing_count_windows_days"],
                                   feats["features"]["days_since_last_cap"])
    rows = rows.merge(cell_regions(grid, rows["cell_id"], boundary), on="cell_id", how="left")
    fallback = det.groupby("cell_id")["region"].agg(lambda s: s.mode().iloc[0])
    rows["cell_region"] = rows["cell_region"].fillna(rows["cell_id"].map(fallback))

    b1 = FrozenLogistic.load(MODEL)               # locked B1, frozen and hash-checked
    rows["p_B1"] = b1.predict(rows).astype("float32") if len(rows) else []

    rows["label_final"] = [label_final(d.date(), now, lag) for d in rows["date"]]
    rows["label"] = rows["label"].astype("Int64").mask(~rows["label_final"])
    rc = rows["cell_id"].str.extract(r"^r(-?\d+)_c(-?\d+)$").astype(int)
    rows["lat"] = (grid.origin_lat + (rc[0] + 0.5) * grid.resolution_deg).astype("float32")
    rows["lon"] = (grid.origin_lon + (rc[1] + 0.5) * grid.resolution_deg).astype("float32")

    out = data_dir() / "live"
    out.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(out / "live_scores.parquet", index=False)
    det.drop(columns=["available_at_utc"]).to_parquet(out / "live_detections.parquet", index=False)

    latest_acq = det.groupby("source")["acq_datetime_utc"].max()
    meta = {
        "run_at_utc": now.isoformat(timespec="seconds"),
        "window": [first.isoformat(), today.isoformat()],
        "scored_days": [start.isoformat(), today.isoformat()],
        "nrt_lag_hours": lag,
        "model": b1.spec["model_id"],
        "model_sha256": b1.spec["sha256"],
        "latest_acquisition_utc": {s: t.isoformat() for s, t in latest_acq.items()},
        "last_retrieval_utc": inventory.groupby("source")["retrieved_at_utc"].max().to_dict() if len(inventory) else {},
        "unobserved_days": [d.date().isoformat() for d in unobserved],
        "rows": len(rows),
        "rows_label_pending": int((~rows["label_final"]).sum()),
        "detections": info,
    }
    (out / "live_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    td = rows[rows["date"].dt.date == today]
    print(f"Scored {len(rows):,} cell-days {start}..{today}; today ({today}): {len(td):,} cells, "
          f"{int((td['p_B1'] >= td['p_B1'].quantile(0.9)).sum()) if len(td) else 0} in top 10%")
    print(f"Latest acquisitions: {meta['latest_acquisition_utc']}; unobserved days: {meta['unobserved_days']}")


if __name__ == "__main__":
    main()
