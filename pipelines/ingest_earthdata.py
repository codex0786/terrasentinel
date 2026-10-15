"""Download NASA Earthdata granules (via earthaccess) over the India bbox into the raw archive.

    python pipelines/ingest_earthdata.py --short-name VNP64A1 --version 002 --start 2024-01-01 --end 2024-12-31
"""

from __future__ import annotations

import argparse

from terrasentinel.config import data_dir, load_dotenv, load_yaml
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.ingestion.earthdata import fetch_granules, login


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--short-name", required=True)
    p.add_argument("--version")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--max-granules", type=int, default=500)
    args = p.parse_args()

    load_dotenv()
    login()
    b = load_yaml("india.yaml")["region"]["bbox"]
    recs = fetch_granules(RawArchive(data_dir() / "raw"), args.short_name, args.version,
                          (b["west"], b["south"], b["east"], b["north"]), (args.start, args.end), args.max_granules)
    print(f"Archived {len(recs)} new granule(s), {sum(r.size_bytes for r in recs) / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
