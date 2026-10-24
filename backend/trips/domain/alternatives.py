"""Fallback route generation: where to ask the router to avoid, and whether a candidate is a
genuinely useful third option rather than a forced detour."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
import shapely

from .geo import LatLon, LocalProjection, haversine_mi
from .sampling import Track

DISTINCT_AWAY_MI = 1.0  # a sample further than this from every existing route counts as distinct
MIN_DISTINCT_SHARE = 0.25
# The brief asks for three options, so a fallback route may be up to 50% longer than the fastest;
# anything over 30% longer is labelled a long detour so the trade-off is visible.
MAX_DETOUR_RATIO = 1.5
LONG_DETOUR_RATIO = 1.3
BACKTRACK_STEP_MI = 10.0


@dataclass(frozen=True)
class Rect:
    south: float
    west: float
    north: float
    east: float


def avoid_rects(
    track: Track,
    *,
    start_frac: float = 0.3,
    end_frac: float = 0.7,
    max_rects: int = 4,
    max_chunk_mi: float = 80.0,
) -> list[Rect]:
    """Rectangles covering the middle stretch of `track`, clear of origin and destination.

    Chunks are at most 80 route-miles, so each padded box stays inside TomTom's ~160 km limit.
    """
    total = track.total_mi
    span = (end_frac - start_frac) * total
    chunk = min(max_chunk_mi, span / max_rects) if span > 0 else 0
    if chunk <= 0:
        return []
    covered = chunk * max_rects
    start = total / 2 - covered / 2
    pad_mi = min(5.0, 0.05 * total)
    rects = []
    for k in range(max_rects):
        a, b = start + k * chunk, start + (k + 1) * chunk
        miles = np.linspace(a, b, 12)
        pts = np.array([track.point_at(m) for m in miles])
        lat_pad = pad_mi / 69.0
        lon_pad = pad_mi / (69.0 * max(0.2, np.cos(np.radians(pts[:, 0].mean()))))
        rects.append(
            Rect(
                south=float(pts[:, 0].min() - lat_pad),
                west=float(pts[:, 1].min() - lon_pad),
                north=float(pts[:, 0].max() + lat_pad),
                east=float(pts[:, 1].max() + lon_pad),
            )
        )
    return rects


def _samples(track: Track, step_mi: float) -> list[LatLon]:
    count = max(2, int(track.total_mi / step_mi) + 1)
    return [track.point_at(m) for m in np.linspace(0, track.total_mi, count)]


def distinct_share(candidate: Track, existing: Sequence[Track], step_mi: float = 1.0) -> float:
    """Fraction of the candidate's length more than DISTINCT_AWAY_MI from all existing routes."""
    if not existing:
        return 1.0
    samples = _samples(candidate, step_mi)
    proj = LocalProjection(float(np.mean([p[0] for p in samples])))
    points = shapely.points(proj.to_xy(samples))
    nearest = np.full(len(samples), np.inf)
    for track in existing:
        line = shapely.LineString(proj.to_xy(track.points))
        nearest = np.minimum(nearest, shapely.distance(points, line))
    return float(np.mean(nearest > DISTINCT_AWAY_MI))


def backtrack_mi(track: Track, step_mi: float = BACKTRACK_STEP_MI) -> float:
    """Total distance gained *away* from the destination, measured every `step_mi`."""
    destination = track.points[-1]
    gaps = [haversine_mi(p, destination) for p in _samples(track, step_mi)]
    return float(sum(max(0.0, b - a) for a, b in pairwise(gaps)))


def detour_ratio(track: Track, fastest: Track) -> float:
    """How much longer `track` is than `fastest`, by time or distance, whichever is worse."""
    ratios = [1.0]
    if fastest.duration_s > 0:
        ratios.append(track.duration_s / fastest.duration_s)
    if fastest.total_mi > 0:
        ratios.append(track.total_mi / fastest.total_mi)
    return max(ratios)


def rejection_reason(candidate: Track, existing: Sequence[Track]) -> str | None:
    """Why `candidate` should not be offered as an extra route, or None if it is acceptable."""
    fastest = min(existing, key=lambda t: t.duration_s)
    if candidate.duration_s > MAX_DETOUR_RATIO * fastest.duration_s:
        return "too slow compared with the fastest route"
    if candidate.total_mi > MAX_DETOUR_RATIO * fastest.total_mi:
        return "too long compared with the fastest route"
    if distinct_share(candidate, existing) < MIN_DISTINCT_SHARE:
        return "not distinct enough from the existing routes"
    if backtrack_mi(candidate) > max(5.0, 0.02 * candidate.total_mi):
        return "doubles back on itself"
    return None
