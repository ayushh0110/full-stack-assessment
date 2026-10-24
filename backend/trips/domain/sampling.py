"""Route tracks, checkpoint placement and ETA interpolation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from . import geo
from .geo import METERS_PER_MILE, LatLon

# An interval checkpoint this close to the destination is replaced by the destination itself.
DESTINATION_MERGE_MI = 1.0


@dataclass(frozen=True)
class Track:
    """A route polyline with the distance (miles) and elapsed driving time (seconds) at every
    vertex."""

    points: list[LatLon]
    cum_mi: np.ndarray
    elapsed_s: np.ndarray

    @property
    def total_mi(self) -> float:
        return float(self.cum_mi[-1])

    @property
    def duration_s(self) -> float:
        return float(self.elapsed_s[-1])

    def point_at(self, mile: float) -> LatLon:
        return geo.point_at(self.points, self.cum_mi, mile)

    def elapsed_at(self, mile: float) -> float:
        return float(np.interp(mile, self.cum_mi, self.elapsed_s))

    def subset(self, indices: Sequence[int]) -> Track:
        idx = list(indices)
        return Track([self.points[i] for i in idx], self.cum_mi[idx], self.elapsed_s[idx])

    def simplified(self, tolerance_deg: float) -> Track:
        return self.subset(geo.simplify_indices(self.points, tolerance_deg))


@dataclass(frozen=True)
class Slot:
    """Where a checkpoint sits on its route and which stretch of road it represents."""

    mile: float
    from_mi: float
    to_mi: float
    lat: float
    lon: float
    elapsed_s: float


def checkpoint_miles(total_mi: float, interval_mi: float) -> list[float]:
    """Mileposts for checkpoints: the origin, every `interval_mi`, and always the destination."""
    if total_mi <= 0:
        return [0.0]
    miles = [0.0]
    k = 1
    while total_mi - k * interval_mi > DESTINATION_MERGE_MI:
        miles.append(float(k * interval_mi))
        k += 1
    miles.append(float(total_mi))
    return miles


def attribution_bounds(miles: Sequence[float]) -> list[tuple[float, float]]:
    """Each checkpoint owns the road halfway to its neighbours, so the stretches tile the route
    exactly. Risk miles are therefore attributed miles, not a continuous observation."""
    if len(miles) == 1:
        return [(miles[0], miles[0])]
    mids = [(a + b) / 2 for a, b in pairwise(miles)]
    starts = [miles[0], *mids]
    ends = [*mids, miles[-1]]
    return list(zip(starts, ends, strict=True))


def place_checkpoints(track: Track, interval_mi: float) -> list[Slot]:
    miles = checkpoint_miles(track.total_mi, interval_mi)
    slots = []
    for mile, (start, end) in zip(miles, attribution_bounds(miles), strict=True):
        lat, lon = track.point_at(mile)
        slots.append(Slot(mile, start, end, lat, lon, track.elapsed_at(mile)))
    return slots


def build_time_profile(
    cum_mi: np.ndarray,
    duration_s: float,
    progress: Sequence[tuple[int, float]] | None = None,
    instruction_anchors: Sequence[tuple[float, float]] | None = None,
) -> tuple[np.ndarray, str]:
    """Elapsed seconds at every vertex, best source first:

    1. `progress`: (point index, elapsed s) pairs from the routing engine's travel-time profile;
    2. `instruction_anchors`: (offset m, elapsed s) at guidance instructions;
    3. time proportional to distance.

    Between known anchors, time is interpolated linearly by distance.
    """
    total = float(cum_mi[-1]) if len(cum_mi) else 0.0
    n = len(cum_mi)
    anchors: list[tuple[float, float]] = []
    source = "proportional"
    if progress and len(progress) >= 2 and all(0 <= i < n for i, _ in progress):
        anchors = [(float(cum_mi[i]), float(s)) for i, s in progress]
        source = "progress"
    elif instruction_anchors and len(instruction_anchors) >= 2:
        anchors = [(m / METERS_PER_MILE, float(s)) for m, s in instruction_anchors]
        source = "instructions"

    anchors.sort()
    if not anchors or anchors[0][0] > 1e-9:
        anchors.insert(0, (0.0, 0.0))
    if anchors[-1][0] < total - 1e-9:
        anchors.append((total, float(duration_s)))

    xs, ys = [anchors[0][0]], [anchors[0][1]]
    for x, y in anchors[1:]:
        if x > xs[-1]:
            xs.append(x)
            ys.append(max(y, ys[-1]))  # time never runs backwards
    if len(xs) == 1:
        return np.zeros(n), source
    return np.interp(cum_mi, xs, ys), source
