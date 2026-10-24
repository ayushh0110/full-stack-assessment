"""Synthetic geometry for tests: straight routes along a meridian with known mileage."""

from __future__ import annotations

import math

import numpy as np

from trips.domain.geo import MILES_PER_DEG_LAT, cumulative_mi
from trips.domain.sampling import Track


def line_points(total_mi: float, n: int = 101, lat0: float = 35.0, lon: float = -100.0):
    dlat = total_mi / MILES_PER_DEG_LAT
    return [(lat0 + dlat * i / (n - 1), lon) for i in range(n)]


def track_from_points(points, speed_mph: float = 50.0) -> Track:
    cum = cumulative_mi(points)
    return Track(list(points), cum, cum / speed_mph * 3600)


def straight_track(
    total_mi: float = 100.0, n: int = 101, speed_mph: float = 50.0, lon_offset_mi: float = 0.0
) -> Track:
    lat0 = 35.0
    lon = -100.0 + lon_offset_mi / (MILES_PER_DEG_LAT * math.cos(math.radians(lat0)))
    return track_from_points(line_points(total_mi, n, lat0, lon), speed_mph)


def scaled(track: Track, time_factor: float) -> Track:
    return Track(track.points, track.cum_mi, np.asarray(track.elapsed_s) * time_factor)
