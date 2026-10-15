"""Synthetic boundaries and fire worlds for tests (no real data)."""

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from terrasentinel.geospatial.boundary import load_boundary


def two_states(tmp_path):
    gdf = gpd.GeoDataFrame({"shapeName": ["StateA", "StateB"]},
                           geometry=[box(70, 10, 80, 20), box(80, 10, 90, 20)], crs="EPSG:4326")
    path = tmp_path / "states.geojson"
    gdf.to_file(path, driver="GeoJSON")
    return load_boundary(path, "shapeName")


def synthetic_fire_world(n_cells=60, start="2021-01-01", end="2023-12-31", seed=0, signal=True):
    """Markov fire process per cell. 'Big' cells persist more and produce more detections, so
    trailing counts carry real signal about persistence when signal=True."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D", tz="UTC")
    rows = []
    for c in range(n_cells):
        lat = 11.05 + (c // 20) * 0.5
        lon = 71.05 + (c % 20) * 0.9          # spans both states
        big = c % 3 == 0
        on = False
        for d in days:
            season = d.month in (3, 4, 5)
            if on:
                p = (0.85 if big else 0.25) if signal else 0.5
            else:
                p = 0.06 if season else 0.004
            on = rng.random() < p
            if on:
                n = 1 + rng.poisson(6 if (big and signal) else 1.5)
                for _ in range(n):
                    rows.append((lat + rng.uniform(-0.04, 0.04), lon + rng.uniform(-0.04, 0.04),
                                 d + pd.Timedelta(minutes=int(rng.integers(0, 1440))),
                                 rng.uniform(1, 50 if big else 10)))
    df = pd.DataFrame(rows, columns=["latitude", "longitude", "acq_datetime_utc", "frp"])
    return df.assign(confidence_class="nominal", source="SYNTH")
