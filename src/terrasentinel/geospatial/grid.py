"""Regular latitude/longitude analysis grid.

Cells are half-open: a point on a cell's south/west edge belongs to that cell,
a point on its north/east edge belongs to the neighbour.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_EPS = 1e-9  # guards against binary floating error, e.g. 6.3 / 0.1 = 62.999999...


@dataclass(frozen=True)
class Grid:
    resolution_deg: float
    origin_lon: float
    origin_lat: float

    @classmethod
    def from_config(cls, cfg: dict) -> Grid:
        g = cfg["grid"]
        return cls(float(g["resolution_deg"]), float(g["origin_lon"]), float(g["origin_lat"]))

    def index(self, lat, lon) -> tuple[np.ndarray, np.ndarray]:
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        row = np.floor((lat - self.origin_lat) / self.resolution_deg + _EPS).astype(np.int64)
        col = np.floor((lon - self.origin_lon) / self.resolution_deg + _EPS).astype(np.int64)
        return row, col

    def cell_id(self, lat, lon) -> np.ndarray:
        row, col = self.index(lat, lon)
        return np.char.add(np.char.add("r", row.astype(str)), np.char.add("_c", col.astype(str)))

    def cell_center(self, row: int, col: int) -> tuple[float, float]:
        r = self.resolution_deg
        return (self.origin_lat + (row + 0.5) * r, self.origin_lon + (col + 0.5) * r)


def in_bbox(df: pd.DataFrame, bbox: dict) -> pd.Series:
    return (df["longitude"].between(bbox["west"], bbox["east"])
            & df["latitude"].between(bbox["south"], bbox["north"]))
