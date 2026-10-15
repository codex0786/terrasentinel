"""Download India's state (ADM1) boundaries from geoBoundaries into the raw archive.

Default: geoBoundaries gbOpen IND ADM1 (source: DataMeet India community / Election Commission
of India; licence CC BY 2.5 IN; year represented 2011, per the geoBoundaries API on 2026-10-15).
The depiction of disputed areas differs between sources. Record the choice in
docs/data_provenance.md before reporting any India-level statistic.
"""

from __future__ import annotations

import argparse
import json

import requests

from terrasentinel.config import data_dir, load_yaml
from terrasentinel.ingestion.archive import RawArchive, sha256_bytes
from terrasentinel.ingestion.http import fetch_with_retry

API = "https://www.geoboundaries.org/api/current/gbOpen/IND/{level}/"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--level", default="ADM1", choices=["ADM0", "ADM1", "ADM2"])
    p.add_argument("--simplified", action="store_true", help="use the simplified geometry (smaller, coarser)")
    p.add_argument("--pinned", action="store_true",
                   help="download the study's commit-pinned file and verify its sha256 (used by the daily job)")
    args = p.parse_args()

    if args.pinned:
        pin = load_yaml("data_sources.yaml")["geoboundaries"]["pinned"][args.level]
        content = fetch_with_retry(pin["url"], timeout_s=300)
        if sha256_bytes(content) != pin["sha256"]:
            raise SystemExit(f"{args.level}: downloaded file does not match the pinned sha256; refusing to use it")
        rec = RawArchive(data_dir() / "raw").store("geoboundaries", f"IND_{args.level}", content,
                                                   {"url": pin["url"], "pinned": True}, suffix=".geojson")
        print(f"Pinned {args.level} verified and archived -> data/raw/{rec.path}")
        return

    meta = requests.get(API.format(level=args.level), timeout=60)
    meta.raise_for_status()
    info = meta.json()
    url = info["simplifiedGeometryGeoJSON" if args.simplified else "gjDownloadURL"]
    content = fetch_with_retry(url, timeout_s=300)
    json.loads(content)  # must be valid GeoJSON before it is archived

    request = {k: info.get(k) for k in ("boundaryID", "boundaryName", "boundaryType", "boundarySource",
                                        "boundaryLicense", "boundaryYearRepresented", "admUnitCount")}
    request["url"] = url
    rec = RawArchive(data_dir() / "raw").store("geoboundaries", f"IND_{args.level}", content, request,
                                               suffix=".geojson")
    print(f"{info.get('boundaryName')} {args.level}: {info.get('admUnitCount')} units, "
          f"licence {info.get('boundaryLicense')}")
    print(f"Archived {rec.size_bytes} B -> data/raw/{rec.path}")
    print("Set region.boundary_file in configs/india.yaml to that path (relative to the data dir).")


if __name__ == "__main__":
    main()
