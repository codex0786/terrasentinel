"""Milestone 1 source smoke test: is FIRMS reachable with this key, and does a bounded
one-day India request return a parseable, schema-valid CSV?

Writes the response to the raw archive (it is real data) and prints a short summary.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta

import requests

from terrasentinel.config import data_dir, load_dotenv, load_yaml, require_env
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.ingestion.firms import BASE_URL, BBox, FirmsClient
from terrasentinel.validation.firms_schema import normalize_firms, read_firms_csv


def main() -> int:
    load_dotenv()
    key = require_env("FIRMS_MAP_KEY")
    archive = RawArchive(data_dir() / "raw")
    bbox = BBox(**load_yaml("india.yaml")["region"]["bbox"])

    try:
        status = requests.get(f"{BASE_URL}/mapserver/mapkey_status/", params={"MAP_KEY": key}, timeout=30)
        print("MAP_KEY status:", json.dumps(status.json()) if status.ok else f"HTTP {status.status_code}")
    except (requests.RequestException, ValueError) as exc:
        print(f"MAP_KEY status check unavailable ({type(exc).__name__}); continuing")

    day = datetime.now(UTC).date() - timedelta(days=2)
    checks = [("VIIRS_SNPP_NRT", day), ("VIIRS_SNPP_SP", date(2024, 3, 15))]
    ok = True
    client = FirmsClient(key, archive)
    for source, d in checks:
        try:
            rec = client.fetch_chunk(source, bbox, d, 1)
            df, rep = normalize_firms(read_firms_csv(archive.read(rec)), source)
            print(f"PASS {source} {d}: {rep.rows_in} rows in, {rep.rows_out} valid, "
                  f"dropped={rep.dropped}, dups={rep.duplicates_removed}, sha256={rec.sha256[:12]}")
        except Exception as exc:  # report every source, then fail overall
            ok = False
            print(f"FAIL {source} {d}: {type(exc).__name__}: {exc}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
