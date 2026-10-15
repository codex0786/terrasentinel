"""Stack archived IMERG daily India subsets into one compressed file per year and audit them:
    data/interim/imerg/imerg_india_<year>.nc   precipitation (mm/day, float32), precipitation_cnt (int8)

The grid is the IMERG native 0.1 deg grid, identical to the project cell grid (cell centres x.x5 deg).

    python pipelines/build_imerg.py [--years 2023 2024]
"""

from __future__ import annotations

import argparse
import io
from collections import defaultdict
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import xarray as xr

from terrasentinel.config import REPO_ROOT, data_dir
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.ingestion.imerg import PRODUCT

DAY = pd.Timedelta(days=1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--years", type=int, nargs="*")
    args = p.parse_args()

    archive = RawArchive(data_dir() / "raw")
    by_year = defaultdict(dict)
    for r in archive.records():
        if r.provider == "earthdata" and r.product == PRODUCT:
            day = pd.Timestamp(r.request["filename"].split(".")[4][:8], tz="UTC")
            by_year[day.year][day] = r
    years = sorted(args.years or by_year)
    out_dir = data_dir() / "interim" / "imerg"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for y in years:
        days = sorted(by_year.get(y, {}))
        expected = pd.date_range(f"{y}-01-01", f"{y}-12-31", freq="D", tz="UTC")
        missing = [d.date().isoformat() for d in expected if d not in by_year.get(y, {})]
        arrays = []
        for d in days:
            ds = xr.open_dataset(io.BytesIO(archive.read(by_year[y][d])), engine="h5netcdf").load()
            arrays.append(ds.assign_coords(time=[d.tz_convert(None)]))
        if not arrays:
            continue
        stack = xr.concat(arrays, dim="time").transpose("time", "lat", "lon")
        stack["precipitation"] = stack["precipitation"].astype("float32")
        enc = {v: {"zlib": True, "complevel": 4} for v in stack.data_vars}
        stack.to_netcdf(out_dir / f"imerg_india_{y}.nc", engine="h5netcdf", encoding=enc)
        pr = stack["precipitation"].values
        cnt = stack["precipitation_cnt"].values
        rows.append({"year": y, "days": len(days), "missing_days": len(missing),
                     "missing_list": ", ".join(missing[:5]) + (" …" if len(missing) > 5 else ""),
                     "nan_frac": float(np.isnan(pr).mean()), "mean_mm_day": float(np.nanmean(pr)),
                     "p99_mm_day": float(np.nanpercentile(pr, 99)), "max_mm_day": float(np.nanmax(pr)),
                     "cnt_lt_24_frac": float((cnt < 24).mean())})
        print(f"{y}: {len(days)} days, missing {len(missing)}", flush=True)

    audit = pd.DataFrame(rows)
    now = datetime.now(UTC)
    lines = [f"# IMERG Final daily (India subset) audit — {now:%Y-%m-%d %H:%M} UTC", "",
             "precipitation_cnt = number of valid half-hourly samples (of 48) behind each daily value; "
             "`cnt_lt_24_frac` = share of cell-days built from fewer than half the samples.", "",
             audit.round(4).to_markdown(index=False)]
    report = REPO_ROOT / "reports" / "audits" / f"imerg_audit_{now:%Y%m%dT%H%M}.md"
    report.write_text("\n".join(lines) + "\n")
    print(audit.drop(columns=["missing_list"]).round(3).to_string(index=False))
    print(f"Wrote {report.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
