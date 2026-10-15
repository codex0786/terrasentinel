"""Data audit (roadmap step 14.4): inspect archived FIRMS data before any modelling.

Processed one source at a time with compact dtypes so ten years of detections fit in memory.
Reports reconciliation, duplicates, key collisions, date coverage, days with zero detections
(possible outages), sensor identity, confidence, day/night, and missingness. Writes a Markdown
report and one normalized Parquet snapshot per source (in-bbox detections):
    data/interim/firms_normalized_<SOURCE>.parquet
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from terrasentinel.config import REPO_ROOT, data_dir, load_yaml
from terrasentinel.geospatial.grid import in_bbox
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.validation.firms_schema import (
    DEDUP_KEY,
    NUMERIC_COLUMNS,
    normalize_firms,
    read_firms_csv,
    sort_canonical,
)

KEEP_FLOAT64 = {"latitude", "longitude"}  # exact values matter for duplicate detection
DERIVED = ("acq_datetime_utc", "confidence_class", "confidence_pct")


def _md_table(s: pd.Series | pd.DataFrame) -> str:
    return s.to_frame().to_markdown() if isinstance(s, pd.Series) else s.to_markdown()


def compact(df: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for c in df.columns:
        s = df[c]
        if c in NUMERIC_COLUMNS and not pd.api.types.is_numeric_dtype(s):
            raise TypeError(f"numeric column {c!r} has dtype {s.dtype}")
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            out[c] = s.astype("category")
        elif pd.api.types.is_float_dtype(s) and c not in KEEP_FLOAT64:
            out[c] = s.astype(np.float32)
        else:
            out[c] = s
    return pd.DataFrame(out)


def requested_days(records) -> set[date]:
    days = set()
    for r in records:
        start = date.fromisoformat(r.request["start_date"])
        days |= {start + timedelta(days=i) for i in range(int(r.request["day_range"]))}
    return days


def audit_source(archive: RawArchive, source: str, records, bbox: dict) -> tuple[pd.DataFrame, list[str]]:
    seen, frames, reports = set(), [], []
    for r in records:
        if r.sha256 in seen:
            continue
        seen.add(r.sha256)
        df, rep = normalize_firms(read_firms_csv(archive.read(r)), source)
        reports.append(rep)
        if len(df):  # header-only responses (no detections) contribute counts, not rows
            frames.append(compact(df))
    det = pd.concat(frames, ignore_index=True)
    for c in det.columns:  # per-file categories differ; unify string columns before comparing rows
        if isinstance(det[c].dtype, pd.CategoricalDtype) or det[c].dtype == object:
            det[c] = det[c].astype(str).astype("category")
    bad = [c for c in NUMERIC_COLUMNS if c in det.columns and not pd.api.types.is_numeric_dtype(det[c])]
    if bad:
        raise TypeError(f"{source}: numeric columns lost their type: {bad}")
    raw_cols = [c for c in det.columns if c not in DERIVED]
    cross_file_dups = int(det.duplicated(subset=raw_cols).sum())
    det = sort_canonical(det.drop_duplicates(subset=raw_cols))
    key_collisions = int(det.duplicated(subset=list(DEDUP_KEY), keep=False).sum())
    inside = det[in_bbox(det, bbox)].reset_index(drop=True)

    req = requested_days(records)
    daily = inside["acq_datetime_utc"].dt.date.value_counts()
    zero_days = sorted(d for d in req if d not in daily.index)
    yearly = inside.groupby(inside["acq_datetime_utc"].dt.year).agg(
        detections=("latitude", "size"),
        days_with_detections=("acq_datetime_utc", lambda s: s.dt.date.nunique()),
        frp_median=("frp", "median"),
    )
    lines = [
        f"## {source}", "",
        f"Archived files read: {len(seen)} (manifest entries: {len(records)}); "
        f"requested days: {len(req)} ({min(req)}..{max(req)})", "",
        f"- rows in: {sum(r.rows_in for r in reports):,}; rows out: {sum(r.rows_out for r in reports):,}",
        f"- within-file duplicates removed: {sum(r.duplicates_removed for r in reports):,}",
        f"- cross-file duplicates removed: {cross_file_dups:,}",
        f"- key collisions kept (same key, different values): {key_collisions:,}",
        f"- dropped: {pd.Series([r.dropped for r in reports]).apply(pd.Series).sum().to_dict()}",
        f"- unexpected columns: {sorted({c for r in reports for c in r.unexpected_columns})}",
        f"- detections inside study bbox: {len(inside):,} of {len(det):,}", "",
        f"**Requested days with zero detections in the bbox: {len(zero_days)}** "
        "(possible outages; zero over this whole region is implausible for a real fire-free day)", "",
        _md_table(pd.Series(_ranges(zero_days), name="zero-detection ranges")) if zero_days else "_none_", "",
        "### Per year", "", _md_table(yearly), "",
        "### Confidence class", "", _md_table(inside["confidence_class"].value_counts().rename("n")), "",
        "### Satellite / day-night", "",
        _md_table(inside.groupby(["satellite", "daynight"], observed=True).size().rename("n")), "",
        "### Missingness (fraction null, non-zero only)", "",
        _md_table(inside.isna().mean().pipe(lambda s: s[s > 0]).round(4).rename("null_frac"))
        if inside.isna().any().any() else "_none_", "",
    ]
    return inside, lines


def _ranges(days: list[date]) -> list[str]:
    out, start, prev = [], None, None
    for d in days:
        if start is None:
            start = prev = d
        elif d == prev + timedelta(days=1):
            prev = d
        else:
            out.append(f"{start}..{prev} ({(prev - start).days + 1} d)")
            start = prev = d
    if start is not None:
        out.append(f"{start}..{prev} ({(prev - start).days + 1} d)")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", action="append", help="restrict to these FIRMS sources (repeatable)")
    args = p.parse_args()

    archive = RawArchive(data_dir() / "raw")
    by_source = defaultdict(list)
    for r in archive.records():
        if r.provider == "firms" and (not args.source or r.product in args.source):
            by_source[r.product].append(r)
    if not by_source:
        raise SystemExit("No archived FIRMS files found. Run pipelines/ingest.py first.")

    bbox = load_yaml("india.yaml")["region"]["bbox"]
    now = datetime.now(UTC)
    lines = [f"# FIRMS data audit — {now:%Y-%m-%d %H:%M} UTC", ""]
    out_dir = data_dir() / "interim"
    out_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(by_source):
        inside, section = audit_source(archive, source, by_source[source], bbox)
        lines += section
        inside.to_parquet(out_dir / f"firms_normalized_{source}.parquet", index=False)
        print(f"{source}: {len(inside):,} detections -> interim/firms_normalized_{source}.parquet")
        del inside
    lines += ["## Notes for the protocol", "",
              "- A missing detection is not a confirmed absence of fire (clouds, overpass timing, detection limits).",
              "- Counts are for the bbox; the India boundary is applied in build_dataset.py."]
    report_dir = REPO_ROOT / "reports" / "audits"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"firms_audit_{now:%Y%m%dT%H%M}.md"
    report.write_text("\n".join(lines) + "\n")
    print(f"Wrote {report.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
