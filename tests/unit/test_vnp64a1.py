import io

import h5py
import numpy as np
import pytest

from terrasentinel.validation.vnp64a1 import GRID_PATH, NPIX, parse_name, pixel_latlon, read_tile


def make_tile(burn: dict, unmapped=()):
    bd = np.zeros((NPIX, NPIX), dtype=np.int16)
    unc = np.zeros_like(bd)
    for (r, c), doy in burn.items():
        bd[r, c] = doy
        unc[r, c] = 2
    for r, c in unmapped:
        bd[r, c] = -1
    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        f[GRID_PATH + "Burn Date"] = bd
        f[GRID_PATH + "Burn Date Uncertainty"] = unc
    return buf.getvalue()


def test_parse_name():
    assert parse_name("VNP64A1.A2024092.h24v06.002.2024200.h5") == (2024, 92, 24, 6)


def test_known_tile_corners():
    # Tile h25v06 spans 20N-30N; its top-left pixel sits just below 30N.
    lat, lon = pixel_latlon(25, 6, np.array([0]), np.array([0]))
    assert 29.9 < lat[0] < 30.0 and 80 < lon[0] < 81


def test_read_tile_burned_and_unmapped():
    # April 2024 granule (DOY 92 = 1 Apr in a leap year); burn on DOY 106 = 15 Apr
    content = make_tile({(1200, 1200): 106, (5, 5): 92}, unmapped=[(10, 10), (11, 11)])
    burned, unmapped = read_tile(content, "VNP64A1.A2024092.h25v06.002.x.h5")
    assert sorted(burned["date"].dt.day) == [1, 15] and (burned["date"].dt.month == 4).all()
    assert len(unmapped) == 2 and (unmapped["month"] == 4).all()


def test_burn_outside_month_rejected():
    with pytest.raises(ValueError, match="outside"):
        read_tile(make_tile({(1, 1): 200}), "VNP64A1.A2024092.h25v06.002.x.h5")
