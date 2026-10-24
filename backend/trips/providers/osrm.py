"""OSRM car routing — a keyless development fallback when no TomTom key is configured.

It does not know about trucks or weight, which the API reports (`truck_aware: false`) and the UI
shows. The weather and risk logic is identical either way.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from itertools import accumulate
from typing import Any

import httpx
from django.conf import settings

from trips.domain.alternatives import Rect
from trips.domain.geo import LatLon
from trips.exceptions import UpstreamError

from . import budget
from .http import request
from .types import RawRoute


def parse_route(route: dict[str, Any]) -> RawRoute:
    points = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    durations = [
        d for leg in route.get("legs", []) for d in leg.get("annotation", {}).get("duration", [])
    ]
    progress = None
    if len(durations) == len(points) - 1:
        progress = list(enumerate(accumulate([0.0, *durations])))
    return RawRoute(
        points=points,
        length_m=float(route["distance"]),
        duration_s=float(route["duration"]),
        progress=progress,
    )


class OsrmRouting:
    name = "osrm"
    truck_aware = False
    supports_avoid_areas = False

    def __init__(self, http: httpx.Client | None = None) -> None:
        self.http = http
        self.url = settings.OSRM_URL

    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        depart_at: datetime,
        gross_lb: int,
        *,
        max_alternatives: int = 2,
        avoid: Sequence[Rect] = (),
    ) -> list[RawRoute]:
        budget.consume("osrm")
        coords = f"{origin[1]:.6f},{origin[0]:.6f};{destination[1]:.6f},{destination[0]:.6f}"
        params = {
            "alternatives": str(max_alternatives) if max_alternatives else "false",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "duration",
            "steps": "false",
        }
        try:
            response = request("GET", f"{self.url}/{coords}", params=params, http=self.http)
        except httpx.HTTPError as exc:
            raise UpstreamError("The routing service is unreachable. Try again shortly.") from exc
        data = (
            response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        if response.status_code != 200 or data.get("code") != "Ok":
            message = data.get("message") or "no route found"
            raise UpstreamError(f"The routing service could not plan this route: {message}.")
        return [parse_route(r) for r in data.get("routes", [])]
