"""The grid of cells covering the trip corridor, used for the weather heatmap."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import shapely

from .geo import MILES_PER_DEG_LAT, LatLon, LocalProjection

LATTICE_DEG = 0.05


@dataclass(frozen=True)
class CellGrid:
    centers: list[LatLon]
    step_lat: float
    step_lon: float


def _snap_up(value: float, lattice: float = LATTICE_DEG) -> float:
    return round(math.ceil(value / lattice - 1e-9) * lattice, 6)


def corridor_grid(
    routes: Sequence[Sequence[LatLon]],
    *,
    buffer_mi: float = 30.0,
    max_cells: int = 400,
    min_step_deg: float = 0.1,
) -> CellGrid:
    """Cells whose centres lie within `buffer_mi` of any route.

    Cell spacing grows with the corridor's area so the count stays at or under `max_cells`, and
    centres sit on a global lattice (multiples of the step), so the same corridor always yields
    the same cells and their forecasts can be cached.
    """
    lines = [r for r in routes if len(r) >= 2]
    if not lines:
        return CellGrid([], min_step_deg, min_step_deg)
    lat0 = float(np.mean([p[0] for r in lines for p in r]))
    proj = LocalProjection(lat0)
    corridor = shapely.union_all(
        [shapely.LineString(proj.to_xy(r)).buffer(buffer_mi, quad_segs=4) for r in lines]
    )
    shapely.prepare(corridor)
    min_x, min_y, max_x, max_y = corridor.bounds
    south, west = proj.to_latlon(min_x, min_y)
    north, east = proj.to_latlon(max_x, max_y)
    cos_lat = max(0.2, math.cos(math.radians(lat0)))

    step_mi = max(min_step_deg * MILES_PER_DEG_LAT, math.sqrt(corridor.area / max_cells))
    step_lat = _snap_up(step_mi / MILES_PER_DEG_LAT)
    while True:
        step_lon = _snap_up(step_lat / cos_lat)
        lats = (
            np.arange(math.floor(south / step_lat), math.ceil(north / step_lat)) + 0.5
        ) * step_lat
        lons = (np.arange(math.floor(west / step_lon), math.ceil(east / step_lon)) + 0.5) * step_lon
        grid_lat, grid_lon = np.meshgrid(lats, lons, indexing="ij")
        flat_lat, flat_lon = grid_lat.ravel(), grid_lon.ravel()
        xy = proj.to_xy(np.column_stack([flat_lat, flat_lon]))
        inside = shapely.contains_xy(corridor, xy[:, 0], xy[:, 1])
        if inside.sum() <= max_cells:
            break
        step_lat = round(step_lat + LATTICE_DEG, 6)

    centers = [
        (round(float(a), 5), round(float(b), 5))
        for a, b in zip(flat_lat[inside], flat_lon[inside], strict=True)
    ]
    return CellGrid(centers, step_lat, step_lon)
