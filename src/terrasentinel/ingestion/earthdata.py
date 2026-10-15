"""NASA Earthdata granule ingestion via earthaccess (VNP64A1, IMERG, MOD13Q1, ...).

Credentials come only from the environment (EARTHDATA_USERNAME / EARTHDATA_PASSWORD) or ~/.netrc.
Each granule is stored once in the raw archive (checksummed, read-only) with its CMR identity, so
re-runs skip granules already archived.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from terrasentinel.ingestion.archive import ArchiveRecord, RawArchive


def login():
    import earthaccess

    if os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"):
        auth = earthaccess.login(strategy="environment")
    else:
        auth = earthaccess.login(strategy="netrc")
    if not auth or not auth.authenticated:
        raise RuntimeError("Earthdata login failed: set EARTHDATA_USERNAME/EARTHDATA_PASSWORD in .env")
    return auth


def granule_id(g) -> str:
    return g["umm"]["GranuleUR"]


def archived_granules(archive: RawArchive, provider: str = "earthdata") -> set[str]:
    return {r.request["granule_ur"] for r in archive.records()
            if r.provider == provider and (archive.root / r.path).exists()}


def fetch_granules(archive: RawArchive, short_name: str, version: str | None, bbox: tuple, temporal: tuple,
                   max_granules: int = 500) -> list[ArchiveRecord]:
    """Search CMR and archive every matching granule not yet archived. bbox = (W, S, E, N)."""
    import earthaccess

    found = earthaccess.search_data(short_name=short_name, version=version, bounding_box=bbox,
                                    temporal=temporal, count=max_granules + 1)
    if len(found) > max_granules:
        raise ValueError(f"{short_name}: more than {max_granules} granules match; narrow the request")
    have = archived_granules(archive)
    todo = [g for g in found if granule_id(g) not in have]
    print(f"{short_name}: {len(found)} granule(s) match, {len(todo)} to download", flush=True)
    records = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, g in enumerate(todo, 1):
            paths = earthaccess.download([g], local_path=tmp, show_progress=False)
            if len(paths) != 1:
                raise RuntimeError(f"expected one file for {granule_id(g)}, got {paths}")
            p = Path(paths[0])
            request = {"short_name": short_name, "version": version, "granule_ur": granule_id(g),
                       "filename": p.name, "bbox": list(bbox), "temporal": list(temporal)}
            rec = archive.store("earthdata", short_name, p.read_bytes(), request, suffix=p.suffix or ".bin")
            p.unlink()
            records.append(rec)
            print(f"  [{i}/{len(todo)}] {p.name} {rec.size_bytes / 1e6:.1f} MB", flush=True)
    return records
