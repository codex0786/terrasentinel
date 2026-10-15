"""Normalize archived NASA POWER regional files into one daily table:
    data/interim/power_daily.parquet   columns: lat, lon, date, T2M_MAX, RH2M, WS2M, PRECTOTCORR

Processed one parameter at a time. Grid points on shared tile edges appear in two files; their
values must agree exactly (otherwise this is an error, not a silent pick).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

import pandas as pd

from terrasentinel.config import REPO_ROOT, data_dir, load_yaml
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.validation.power_schema import parse_power_csv


def main() -> None:
    params = load_yaml("data_sources.yaml")["nasa_power"]["parameters"]
    archive = RawArchive(data_dir() / "raw")
    by_param = defaultdict(list)
    for r in archive.records():
        if r.provider == "nasa_power":
            by_param[r.product].append(r)
    missing = [p for p in params if p not in by_param]
    if missing:
        raise SystemExit(f"No archived POWER data for {missing}. Run pipelines/ingest_power.py first.")

    wide, lines = None, [f"# NASA POWER normalization — {datetime.now(UTC):%Y-%m-%d %H:%M} UTC", ""]
    for p in params:
        seen, frames, n_missing = set(), [], 0
        for r in by_param[p]:
            if r.sha256 in seen:
                continue
            seen.add(r.sha256)
            df, rep = parse_power_csv(archive.read(r), p)
            frames.append(df)
            n_missing += rep.missing
        long = pd.concat(frames, ignore_index=True)
        n_rows = len(long)
        dup = long.duplicated(["lat", "lon", "date"], keep=False)
        conflicts = long[dup].groupby(["lat", "lon", "date"])["value"].nunique(dropna=False)
        if (conflicts > 1).any():
            raise ValueError(f"{p}: {int((conflicts > 1).sum())} edge points disagree between tiles")
        long = long.drop_duplicates(["lat", "lon", "date"]).set_index(["lat", "lon", "date"])["value"].rename(p)
        lines += [f"## {p}", "",
                  f"- files: {len(seen)}; rows: {n_rows:,}; tile-edge duplicates removed (values identical): "
                  f"{n_rows - len(long):,}",
                  f"- missing (-999): {n_missing:,} ({long.isna().mean():.4%})",
                  f"- grid points: {long.index.droplevel('date').nunique():,}; "
                  f"days: {long.index.get_level_values('date').nunique():,} "
                  f"({long.index.get_level_values('date').min().date()}..{long.index.get_level_values('date').max().date()})",
                  f"- range: {long.min():.2f} .. {long.max():.2f}; median {long.median():.2f}", ""]
        wide = long.to_frame() if wide is None else wide.join(long, how="outer")
        del frames, long
        print(f"{p}: done", flush=True)

    wide = wide.reset_index()
    out = data_dir() / "interim" / "power_daily.parquet"
    wide.to_parquet(out, index=False)
    lines += [f"Combined: {len(wide):,} point-days, columns {list(wide.columns)}",
              f"Rows with any variable missing: {wide[params].isna().any(axis=1).mean():.4%}"]
    report = REPO_ROOT / "reports" / "audits" / f"power_audit_{datetime.now(UTC):%Y%m%dT%H%M}.md"
    report.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[2:]))
    print(f"Wrote {out} and {report.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
