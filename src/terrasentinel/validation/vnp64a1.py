"""Read VNP64A1 (VIIRS burned area, monthly, 500 m, MODIS sinusoidal grid) into per-cell burn records.

Burn Date layer values: day of year (1-366) = burned that day; 0 = unburned; -1 = unmapped (insufficient
data); -2 = water. Unmapped pixels are kept as *unknown*, not as *unburned*.
"""

from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

R_EARTH = 6371007.181          # MODIS sinusoidal sphere radius (m)
TILE_M = 1111950.5197665       # tile width (m)
NPIX = 2400                    # 500 m product: 2400 x 2400 pixels per tile
PIX_M = TILE_M / NPIX
X0, Y0 = -20015109.354, 10007554.677
NAME = re.compile(r"\.A(\d{4})(\d{3})\.h(\d{2})v(\d{2})\.")
GRID_PATH = "HDFEOS/GRIDS/VIIRS_Grid_Monthly_500m_BA/Data Fields/"


def parse_name(filename: str) -> tuple[int, int, int, int]:
    """(year, start_doy, h, v) from e.g. VNP64A1.A2024092.h24v06.002.2024191190448.hdf"""
    m = NAME.search(filename)
    if not m:
        raise ValueError(f"not a VNP64A1 tile name: {filename}")
    return tuple(int(x) for x in m.groups())


def pixel_latlon(h: int, v: int, rows: np.ndarray, cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Centre lat/lon (degrees) of sinusoidal pixels."""
    x = X0 + (h * NPIX + cols + 0.5) * PIX_M
    y = Y0 - (v * NPIX + rows + 0.5) * PIX_M
    lat = y / R_EARTH
    lon = x / (R_EARTH * np.cos(lat))
    return np.degrees(lat), np.degrees(lon)


def _read_layers(content: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Burn Date and Burn Date Uncertainty from HDF5 (h5py) or HDF4/HDF-EOS2 (pyhdf, the V002 format)."""
    if content[:8] == b"\x89HDF\r\n\x1a\n":
        import h5py

        with h5py.File(io.BytesIO(content), "r") as f:
            return (f[GRID_PATH + "Burn Date"][()].astype(np.int32),
                    f[GRID_PATH + "Burn Date Uncertainty"][()].astype(np.int32))
    import os
    import tempfile

    from pyhdf.SD import SD, SDC

    with tempfile.NamedTemporaryFile(suffix=".hdf", delete=False) as tmp:
        tmp.write(content)
        path = tmp.name
    try:
        sd = SD(path, SDC.READ)
        try:
            return (sd.select("Burn Date")[:].astype(np.int32),
                    sd.select("Burn Date Uncertainty")[:].astype(np.int32))
        finally:
            sd.end()
    finally:
        os.unlink(path)


def read_tile(content: bytes, filename: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (burned pixels: lat, lon, date, uncertainty_days) and (unmapped pixels: lat, lon, year, month)."""
    year, start_doy, h, v = parse_name(filename)
    bd, unc = _read_layers(content)
    if bd.shape != (NPIX, NPIX):
        raise ValueError(f"{filename}: unexpected grid shape {bd.shape}")
    month = (pd.Timestamp(year, 1, 1) + pd.Timedelta(days=start_doy - 1)).month

    r, c = np.nonzero(bd > 0)
    lat, lon = pixel_latlon(h, v, r, c)
    burned = pd.DataFrame({
        "lat": lat, "lon": lon,
        "date": pd.to_datetime(f"{year}-01-01", utc=True) + pd.to_timedelta(bd[r, c] - 1, unit="D"),
        "uncertainty_days": unc[r, c],
    })
    if len(burned) and (burned["date"].dt.month != month).any():
        raise ValueError(f"{filename}: burn dates outside the granule month")
    ur, uc = np.nonzero(bd == -1)
    ulat, ulon = pixel_latlon(h, v, ur, uc)
    unmapped = pd.DataFrame({"lat": ulat, "lon": ulon, "year": year, "month": month})
    return burned, unmapped
