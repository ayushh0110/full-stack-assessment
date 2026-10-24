"""Distances, interpolation along polylines and simplification."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

LatLon = tuple[float, float]

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344
MILES_PER_DEG_LAT = math.pi * EARTH_RADIUS_MI / 180


def haversine_mi(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def cumulative_mi(points: Sequence[LatLon]) -> np.ndarray:
    """Distance in miles from the first point to every point of the polyline."""
    if len(points) < 2:
        return np.zeros(len(points))
    rad = np.radians(np.asarray(points, dtype=float))
    lat, lon = rad[:, 0], rad[:, 1]
    h = (
        np.sin(np.diff(lat) / 2) ** 2
        + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(np.diff(lon) / 2) ** 2
    )
    segments = 2 * EARTH_RADIUS_MI * np.arcsin(np.minimum(1.0, np.sqrt(h)))
    return np.concatenate([[0.0], np.cumsum(segments)])


def point_at(points: Sequence[LatLon], cum_mi: np.ndarray, mile: float) -> LatLon:
    """Position `mile` miles along the polyline, interpolated within its segment."""
    if mile <= 0:
        return (points[0][0], points[0][1])
    if mile >= cum_mi[-1]:
        return (points[-1][0], points[-1][1])
    i = int(np.searchsorted(cum_mi, mile, side="right")) - 1
    span = cum_mi[i + 1] - cum_mi[i]
    t = 0.0 if span == 0 else (mile - cum_mi[i]) / span
    (lat1, lon1), (lat2, lon2) = points[i], points[i + 1]
    return (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)


def slice_between(
    points: Sequence[LatLon], cum_mi: np.ndarray, start_mi: float, end_mi: float
) -> list[LatLon]:
    """The stretch of polyline between two mileposts, with interpolated end points."""
    lo = int(np.searchsorted(cum_mi, start_mi, side="right"))
    hi = int(np.searchsorted(cum_mi, end_mi, side="left"))
    inner = [(points[k][0], points[k][1]) for k in range(lo, hi)]
    return [point_at(points, cum_mi, start_mi), *inner, point_at(points, cum_mi, end_mi)]


def simplify_indices(points: Sequence[LatLon], tolerance_deg: float) -> list[int]:
    """Douglas–Peucker simplification. Returns the indices of the vertices to keep, so callers
    can carry per-vertex data (distance, elapsed time) across to the simplified line."""
    n = len(points)
    if n <= 2:
        return list(range(n))
    pts = np.asarray(points, dtype=float).copy()
    pts[:, 1] *= math.cos(math.radians(float(pts[:, 0].mean())))
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        a, b = pts[start], pts[end]
        inner = pts[start + 1 : end]
        ab = b - a
        length_sq = float(ab @ ab)
        if length_sq == 0:
            dist = np.hypot(*(inner - a).T)
        else:
            t = np.clip(((inner - a) @ ab) / length_sq, 0.0, 1.0)
            dist = np.hypot(*(inner - (a + t[:, None] * ab)).T)
        k = int(np.argmax(dist))
        if dist[k] > tolerance_deg:
            split = start + 1 + k
            keep[split] = True
            stack.append((start, split))
            stack.append((split, end))
    return np.flatnonzero(keep).tolist()


class LocalProjection:
    """Equirectangular projection to miles around a reference latitude. Accurate enough for
    corridor-scale buffering and distance checks."""

    def __init__(self, lat0: float) -> None:
        self.kx = MILES_PER_DEG_LAT * math.cos(math.radians(lat0))
        self.ky = MILES_PER_DEG_LAT

    def to_xy(self, points: Sequence[LatLon] | np.ndarray) -> np.ndarray:
        arr = np.asarray(points, dtype=float).reshape(-1, 2)
        return np.column_stack([arr[:, 1] * self.kx, arr[:, 0] * self.ky])

    def to_latlon(self, x: float, y: float) -> LatLon:
        return (y / self.ky, x / self.kx)
