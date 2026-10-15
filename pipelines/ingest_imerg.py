"""Download IMERG Final daily India subsets for a range of years (newest first) into the raw archive.

    python pipelines/ingest_imerg.py --first-year 2001 --last-year 2024 --workers 4
"""

from __future__ import annotations

import argparse
import time

from terrasentinel.config import data_dir, load_dotenv, load_yaml
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.ingestion.earthdata import login
from terrasentinel.ingestion.imerg import SHORT_NAME, VERSION, ImergClient


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--first-year", type=int, required=True)
    p.add_argument("--last-year", type=int, required=True)
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()

    import earthaccess

    load_dotenv()
    login()
    bbox = load_yaml("india.yaml")["region"]["bbox"]
    concept = earthaccess.search_datasets(short_name=SHORT_NAME, version=VERSION)[0]["meta"]["concept-id"]
    def fresh_session():
        login()
        return earthaccess.get_requests_https_session()

    client = ImergClient(RawArchive(data_dir() / "raw"), fresh_session(), concept, bbox, session_factory=fresh_session)
    have = client.archived()
    for year in range(args.last_year, args.first_year - 1, -1):
        found = earthaccess.search_data(short_name=SHORT_NAME, version=VERSION,
                                        temporal=(f"{year}-01-01", f"{year}-12-31"), count=400)
        urs = sorted({g["umm"]["GranuleUR"] for g in found if f".{year}" in g["umm"]["GranuleUR"]})
        todo = [u for u in urs if u not in have]
        t = time.time()
        print(f"{year}: {len(urs)} granules, {len(todo)} to fetch", flush=True)
        if todo:
            client.fetch_many(todo, workers=args.workers, log=lambda m: print(m, flush=True))
            print(f"{year}: done in {(time.time() - t) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
