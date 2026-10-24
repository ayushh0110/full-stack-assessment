from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from trips.domain.alternatives import Rect
from trips.domain.geo import LatLon


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class RawRoute:
    """A route as returned by a routing engine, before any analysis."""

    points: list[LatLon]
    length_m: float
    duration_s: float
    progress: list[tuple[int, float]] | None = None  # (point index, elapsed s)
    instruction_anchors: list[tuple[float, float]] | None = None  # (offset m, elapsed s)
    via: str | None = None


class RoutingProvider(Protocol):
    name: str
    truck_aware: bool
    supports_avoid_areas: bool

    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        depart_at: datetime,
        gross_lb: int,
        *,
        max_alternatives: int = 2,
        avoid: Sequence[Rect] = (),
    ) -> list[RawRoute]: ...
