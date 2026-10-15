"""Fetch NASA POWER daily regional meteorology over India into the raw archive.

    python pipelines/ingest_power.py --first-year 2015 --last-year 2024
    python pipelines/ingest_power.py ... --parameters T2M_MAX --dry-run
"""

from __future__ import annotations

import argparse

from terrasentinel.config import data_dir, load_yaml
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.ingestion.power import PowerClient, tiles_for, year_ranges


def main() -> None:
    cfg = load_yaml("data_sources.yaml")["nasa_power"]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--first-year", type=int, required=True)
    p.add_argument("--last-year", type=int, required=True)
    p.add_argument("--parameters", nargs="+", default=cfg["parameters"])
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    tiles = tiles_for(load_yaml("india.yaml")["region"]["bbox"], skip=set(cfg.get("skip_tiles", [])))
    client = PowerClient(RawArchive(data_dir() / "raw"))
    done = client.archived()
    plan = [(prm, t, s, e) for prm in args.parameters for t in tiles
            for s, e in year_ranges(args.first_year, args.last_year)
            if (prm, t.key(), s.isoformat()) not in done]
    print(f"{len(tiles)} tiles x {len(args.parameters)} parameters x years -> {len(plan)} request(s) to make "
          f"({len(done)} already archived)", flush=True)
    if args.dry_run:
        return
    for i, (prm, t, s, e) in enumerate(plan, 1):
        rec = client.fetch(prm, t, s, e)
        print(f"  [{i}/{len(plan)}] {prm} {t.key()} {s.year}: {rec.size_bytes:,} B "
              f"({'new' if rec.newly_written else 'unchanged'})", flush=True)


if __name__ == "__main__":
    main()
