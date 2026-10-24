"""TomTom Routing API (truck mode) — the production routing provider."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from django.conf import settings

from trips.domain.alternatives import Rect
from trips.domain.geo import LatLon
from trips.exceptions import UpstreamError

from . import budget
from .http import request
from .types import RawRoute

BASE_URL = "https://api.tomtom.com/routing/1/calculateRoute"
KG_PER_LB = 0.45359237


def _depart_at(depart_at: datetime) -> str:
    # TomTom rejects departure times in the past; anything up to a minute ahead is "now".
    if depart_at <= datetime.now(UTC) + timedelta(minutes=1):
        return "now"
    return depart_at.astimezone(UTC).isoformat(timespec="seconds")


def _main_road(instructions: list[dict[str, Any]], length_m: float) -> str | None:
    """The road number driven for the longest distance, e.g. "I-80"."""
    meters: dict[str, float] = defaultdict(float)
    for i, step in enumerate(instructions):
        numbers = step.get("roadNumbers") or []
        if not numbers or "routeOffsetInMeters" not in step:
            continue
        end = (
            instructions[i + 1].get("routeOffsetInMeters", length_m)
            if i + 1 < len(instructions)
            else length_m
        )
        meters[numbers[0]] += max(0.0, end - step["routeOffsetInMeters"])
    return max(meters, key=meters.__getitem__) if meters else None


def parse_route(route: dict[str, Any]) -> RawRoute:
    summary = route["summary"]
    points = [
        (p["latitude"], p["longitude"])
        for leg in route.get("legs", [])
        for p in leg.get("points", [])
    ]
    progress = [
        (int(entry["pointIndex"]), float(entry["travelTimeInSeconds"]))
        for entry in route.get("progress", [])
        if "travelTimeInSeconds" in entry
    ]
    instructions = route.get("guidance", {}).get("instructions", [])
    anchors = [
        (float(step["routeOffsetInMeters"]), float(step["travelTimeInSeconds"]))
        for step in instructions
        if "routeOffsetInMeters" in step and "travelTimeInSeconds" in step
    ]
    return RawRoute(
        points=points,
        length_m=float(summary["lengthInMeters"]),
        duration_s=float(summary["travelTimeInSeconds"]),
        progress=progress or None,
        instruction_anchors=anchors or None,
        via=_main_road(instructions, float(summary["lengthInMeters"])),
    )


def _error_message(response: httpx.Response) -> str:
    if response.status_code == 403:
        return "TomTom rejected the API key."
    if response.status_code == 429:
        return "TomTom's rate limit was reached. Try again shortly."
    detail = ""
    try:
        data = response.json()
        detail = (
            data.get("detailedError", {}).get("message")
            or data.get("error", {}).get("description")
            or data.get("errorText", "")
        )
    except ValueError:
        pass
    if "NO_ROUTE_FOUND" in detail:
        return (
            "There's no drivable route between these places. They may be on different "
            "continents or islands; choose an origin and destination connected by road."
        )
    return f"TomTom could not plan this route{': ' + detail if detail else '.'}"


class TomTomRouting:
    name = "tomtom"
    truck_aware = True
    supports_avoid_areas = True

    def __init__(self, api_key: str | None = None, http: httpx.Client | None = None) -> None:
        self.api_key = api_key or settings.TOMTOM_API_KEY
        self.http = http

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
        budget.consume("tomtom_routing")
        url = (
            f"{BASE_URL}/{origin[0]:.6f},{origin[1]:.6f}:"
            f"{destination[0]:.6f},{destination[1]:.6f}/json"
        )
        params = [
            ("key", self.api_key),
            ("travelMode", "truck"),
            ("vehicleCommercial", "true"),
            ("vehicleWeight", str(round(gross_lb * KG_PER_LB))),
            ("maxAlternatives", str(max_alternatives)),
            ("departAt", _depart_at(depart_at)),
            ("traffic", "true"),
            ("routeRepresentation", "polyline"),
            ("extendedRouteRepresentation", "distance"),
            ("extendedRouteRepresentation", "travelTime"),
            ("instructionsType", "coded"),
        ]
        if max_alternatives > 0:
            # TomTom rejects alternativeType on a request that asks for no alternatives.
            params.append(("alternativeType", "anyRoute"))
        try:
            if avoid:
                body = {
                    "avoidAreas": {
                        "rectangles": [
                            {
                                "southWestCorner": {"latitude": r.south, "longitude": r.west},
                                "northEastCorner": {"latitude": r.north, "longitude": r.east},
                            }
                            for r in avoid
                        ]
                    }
                }
                response = request("POST", url, params=params, json=body, http=self.http)
            else:
                response = request("GET", url, params=params, http=self.http)
        except httpx.HTTPError as exc:
            raise UpstreamError("The routing service is unreachable. Try again shortly.") from exc
        if response.status_code != 200:
            raise UpstreamError(_error_message(response))
        return [parse_route(r) for r in response.json().get("routes", [])]
