"""Fetch FIRMS detections over the India bbox into the immutable raw archive.

Examples:
    python pipelines/ingest.py --source VIIRS_SNPP_SP --start 2024-03-01 --end 2024-03-05
    python pipelines/ingest.py --source VIIRS_SNPP_NRT --start 2026-10-10 --end 2026-10-14 --dry-run
"""

from __future__ import annotations

import argparse
from datetime import date

from terrasentinel.config import data_dir, load_dotenv, load_yaml, require_env
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.ingestion.firms import BBox, FirmsClient, iter_date_chunks


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", required=True)
    p.add_argument("--start", required=True, type=date.fromisoformat)
    p.add_argument("--end", required=True, type=date.fromisoformat)
    p.add_argument("--max-requests", type=int, default=200)
    p.add_argument("--dry-run", action="store_true", help="print the planned requests only")
    p.add_argument("--skip-archived", action="store_true",
                   help="skip chunks already in the archive (resume an interrupted ingest; no re-check for revisions)")
    args = p.parse_args()

    region = load_yaml("india.yaml")["region"]
    bbox = BBox(**region["bbox"])
    chunks = list(iter_date_chunks(args.start, args.end))
    print(f"{args.source}: {len(chunks)} request(s) over bbox {bbox.as_param()}")
    if args.dry_run:
        for s, n in chunks:
            print(f"  {s} +{n}d")
        return

    load_dotenv()
    client = FirmsClient(require_env("FIRMS_MAP_KEY"), RawArchive(data_dir() / "raw"))
    recs = client.fetch_range(args.source, bbox, args.start, args.end, args.max_requests, args.skip_archived)
    if args.skip_archived:
        print(f"  {len(chunks) - len(recs)} chunk(s) already archived, skipped")
    for rec in recs:
        state = "new" if rec.newly_written else "unchanged"
        print(f"  {rec.request['start_date']} +{rec.request['day_range']}d  "
              f"{rec.size_bytes:>9} B  sha256={rec.sha256[:12]}  ({state})")


if __name__ == "__main__":
    main()
