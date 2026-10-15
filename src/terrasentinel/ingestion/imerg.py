"""GPM IMERG Final daily (GPM_3IMERGDF v07) India subsets via the Earthdata cloud OPeNDAP service.

Each daily global granule is 3600 (lon) x 1800 (lat) at 0.1 deg; cell centres are at x.x5 deg, so the
India window lines up exactly with the project grid (origin 68.0E, 6.0N, 0.1 deg). Only the window
and the variables needed are transferred (~0.4 MB/day instead of ~32 MB).
Requires the "NASA GESDISC DATA ARCHIVE" application to be approved on the Earthdata account.
"""

from __future__ import annotations

import io
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import numpy as np

from terrasentinel.ingestion.archive import RawArchive

SHORT_NAME, VERSION = "GPM_3IMERGDF", "07"
OPENDAP = "https://opendap.earthdata.nasa.gov/collections/{concept}/granules/{granule}"
VARIABLES = ("precipitation", "precipitation_cnt")
RES = 0.1
PRODUCT = "GPM_3IMERGDF_india"


def window(bbox: dict) -> tuple[int, int, int, int]:
    """Inclusive (lon0, lon1, lat0, lat1) indices for a bbox on the global IMERG grid."""
    lon0 = int(round((bbox["west"] + 180) / RES))
    lon1 = int(round((bbox["east"] + 180) / RES)) - 1
    lat0 = int(round((bbox["south"] + 90) / RES))
    lat1 = int(round((bbox["north"] + 90) / RES)) - 1
    return lon0, lon1, lat0, lat1


def constraint(bbox: dict) -> str:
    x0, x1, y0, y1 = window(bbox)
    parts = [f"/{v}[0][{x0}:{x1}][{y0}:{y1}]" for v in VARIABLES]
    return ";".join(parts + [f"/lon[{x0}:{x1}]", f"/lat[{y0}:{y1}]", "/time"])


def check_subset(content: bytes, bbox: dict) -> None:
    import xarray as xr

    if content[:8] != b"\x89HDF\r\n\x1a\n":
        raise ValueError(f"not a netCDF4 response: {content[:120]!r}")
    ds = xr.open_dataset(io.BytesIO(content), engine="h5netcdf")
    x0, x1, y0, y1 = window(bbox)
    want_lon = -179.95 + RES * np.arange(x0, x1 + 1)
    want_lat = -89.95 + RES * np.arange(y0, y1 + 1)
    if not (np.allclose(ds["lon"].values, want_lon, atol=1e-3) and np.allclose(ds["lat"].values, want_lat, atol=1e-3)):
        raise ValueError("subset coordinates do not match the expected India window")
    p = ds["precipitation"].values
    if np.nanmin(p) < 0 or np.nanmax(p) > 2000:
        raise ValueError(f"implausible precipitation range {np.nanmin(p)}..{np.nanmax(p)} mm/day")


class ImergClient:
    def __init__(self, archive: RawArchive, session, concept_id: str, bbox: dict):
        self.archive, self.session, self.concept, self.bbox = archive, session, concept_id, bbox
        self._lock = threading.Lock()

    def archived(self) -> set[str]:
        return {r.request["granule_ur"] for r in self.archive.records()
                if r.provider == "earthdata" and r.product == PRODUCT and (self.archive.root / r.path).exists()}

    def fetch_one(self, granule_ur: str):
        name = granule_ur.split(":", 1)[1]
        url = OPENDAP.format(concept=self.concept, granule=quote(granule_ur, safe=""))
        for attempt in range(4):
            try:
                r = self.session.get(url + ".dap.nc4", params={"dap4.ce": constraint(self.bbox)}, timeout=300)
                if r.status_code == 200:
                    check_subset(r.content, self.bbox)
                    request = {"short_name": SHORT_NAME, "version": VERSION, "granule_ur": granule_ur,
                               "filename": name, "service": "opendap", "variables": list(VARIABLES),
                               "bbox": self.bbox}
                    with self._lock:
                        return self.archive.store("earthdata", PRODUCT, r.content, request, suffix=".nc4")
                if r.status_code in (401, 403):
                    raise PermissionError(f"HTTP {r.status_code}: approve 'NASA GESDISC DATA ARCHIVE' in Earthdata")
            except PermissionError:
                raise
            except Exception as exc:  # retried below
                last = exc
            else:
                last = RuntimeError(f"HTTP {r.status_code}")
            threading.Event().wait(5 * 2 ** attempt)
        raise RuntimeError(f"{name}: failed after retries: {last}")

    def fetch_many(self, granule_urs: list[str], workers: int = 4, log=print) -> int:
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(self.fetch_one, g): g for g in granule_urs}
            for f in as_completed(futs):
                f.result()
                done += 1
                if done % 50 == 0 or done == len(granule_urs):
                    log(f"  {done}/{len(granule_urs)}")
        return done
