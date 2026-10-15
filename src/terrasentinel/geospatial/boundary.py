"""Administrative boundary handling: clip detections to India and map grid cells to states.

The boundary file is source-agnostic (any polygon layer readable by GeoPandas with a
region-name field). Which boundary is used is a recorded choice; see docs/data_provenance.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import box

from terrasentinel.geospatial.grid import Grid

WGS84 = "EPSG:4326"


@dataclass
class ClipReport:
    rows_in: int = 0
    rows_inside: int = 0
    rows_outside: int = 0
    by_region: dict[str, int] = field(default_factory=dict)


def subdivide(boundary: gpd.GeoDataFrame, tile_deg: float = 1.0) -> gpd.GeoDataFrame:
    """Cut each region into tile_deg x tile_deg pieces. Point-in-polygon results are unchanged, but
    tests against small pieces are ~30x faster than against detailed national outlines.
    Several rows then share a region name."""
    w, s, e, n = boundary.total_bounds
    xs = np.arange(np.floor(w), np.ceil(e), tile_deg)
    ys = np.arange(np.floor(s), np.ceil(n), tile_deg)
    tiles = gpd.GeoDataFrame(geometry=[box(x, y, x + tile_deg, y + tile_deg) for x in xs for y in ys],
                             crs=boundary.crs)
    pieces = gpd.overlay(boundary, tiles, how="intersection", keep_geom_type=True)
    return pieces.explode(index_parts=False)[["region", "geometry"]].reset_index(drop=True)


def load_boundary(path, name_field: str, tile_deg: float | None = 1.0) -> gpd.GeoDataFrame:
    """Load a polygon layer as columns [region, geometry] in WGS84, with invalid geometries repaired.
    By default regions are subdivided into 1-degree pieces for speed (tile_deg=None to disable)."""
    gdf = gpd.read_file(path)
    if name_field not in gdf.columns:
        raise KeyError(f"{name_field!r} not in boundary fields {list(gdf.columns)}")
    gdf = gdf.to_crs(WGS84) if gdf.crs and gdf.crs.to_string() != WGS84 else gdf.set_crs(WGS84, allow_override=True)
    gdf = gdf[[name_field, "geometry"]].rename(columns={name_field: "region"})
    if gdf["region"].isna().any() or gdf["region"].duplicated().any():
        raise ValueError("boundary region names must be non-null and unique")
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].make_valid()
    gdf = gdf.reset_index(drop=True)
    return subdivide(gdf, tile_deg) if tile_deg else gdf


def assign_regions(lat, lon, boundary: gpd.GeoDataFrame) -> pd.Series:
    """Region containing each point (covers: points on a shared edge go to one region), else NaN."""
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(np.asarray(lon), np.asarray(lat)), crs=WGS84)
    joined = gpd.sjoin(pts, boundary, how="left", predicate="covered_by")
    joined = joined[~joined.index.duplicated(keep="first")]  # border points: deterministic first match
    return joined["region"].reindex(pts.index).reset_index(drop=True)


def assign_regions_by_cell(lat, lon, boundary: gpd.GeoDataFrame, grid: Grid) -> pd.Series:
    """Same result as assign_regions, much faster for many points.

    Each grid cell is classified once: wholly within one region -> every point gets that region;
    touching no region -> every point is outside; otherwise (border cell) points are tested exactly.
    """
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    row, col = grid.index(lat, lon)
    cells = pd.DataFrame({"row": row, "col": col}).drop_duplicates().reset_index(drop=True)
    r = grid.resolution_deg
    s, w = grid.origin_lat + cells["row"] * r, grid.origin_lon + cells["col"] * r
    boxes = gpd.GeoDataFrame(cells, geometry=box(w, s, w + r, s + r), crs=WGS84)

    within = gpd.sjoin(boxes, boundary, how="inner", predicate="within")
    within = within[~within.index.duplicated(keep="first")]["region"]
    touching = set(gpd.sjoin(boxes, boundary, how="inner", predicate="intersects").index)
    cells["region"] = within.reindex(cells.index)
    cells["border"] = cells.index.isin(touching) & cells["region"].isna()

    pts = pd.DataFrame({"row": row, "col": col}).merge(cells, on=["row", "col"], how="left")
    out = pts["region"].astype(object)
    need = pts["border"].to_numpy()
    if need.any():
        out[need] = assign_regions(lat[need], lon[need], boundary).to_numpy()
    return out.reset_index(drop=True)


def clip_detections(det: pd.DataFrame, boundary: gpd.GeoDataFrame,
                    grid: Grid | None = None) -> tuple[pd.DataFrame, ClipReport]:
    """Keep detections inside the boundary and add a `region` column. Out-of-boundary rows are counted.
    Pass `grid` for the fast cell-based path (identical results)."""
    if grid is not None:
        region = assign_regions_by_cell(det["latitude"], det["longitude"], boundary, grid)
    else:
        region = assign_regions(det["latitude"], det["longitude"], boundary)
    inside = region.notna().to_numpy()
    out = det.reset_index(drop=True).assign(region=region)[inside].reset_index(drop=True)
    rep = ClipReport(rows_in=len(det), rows_inside=int(inside.sum()), rows_outside=int((~inside).sum()),
                     by_region=out["region"].value_counts().to_dict())
    return out, rep


def cell_regions(grid: Grid, cell_ids: pd.Series, boundary: gpd.GeoDataFrame) -> pd.DataFrame:
    """Map each grid cell to the region containing its centre (NaN if the centre is outside).

    A cell straddling a state border is assigned wholly to the state holding its centre;
    its detections keep their own point-level region for reporting.
    """
    ids = pd.Series(pd.unique(cell_ids), name="cell_id")
    rc = ids.str.extract(r"^r(-?\d+)_c(-?\d+)$").astype(int)
    centers = [grid.cell_center(r, c) for r, c in zip(rc[0], rc[1], strict=True)]
    lat, lon = zip(*centers, strict=True) if centers else ((), ())
    return pd.DataFrame({"cell_id": ids, "cell_region": assign_regions(lat, lon, boundary)})
