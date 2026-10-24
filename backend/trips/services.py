"""Orchestration: providers in, domain logic, API-shaped results out. Views stay thin and the
domain stays free of I/O."""

from __future__ import annotations

import functools
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from django.conf import settings
from timezonefinder import TimezoneFinder

from trips import store
from trips.domain import risk
from trips.domain.alternatives import (
    LONG_DETOUR_RATIO,
    avoid_rects,
    detour_ratio,
    distinct_share,
    rejection_reason,
)
from trips.domain.corridor import CellGrid, corridor_grid
from trips.domain.geo import METERS_PER_MILE, LatLon, cumulative_mi, slice_between
from trips.domain.sampling import Slot, Track, build_time_profile, place_checkpoints
from trips.domain.scoring import (
    Recommendation,
    RouteScore,
    ScoredCheckpoint,
    recommend,
    score_route,
)
from trips.domain.timeutil import HOUR, NonexistentLocalTime, floor_hour, local_to_utc
from trips.domain.weather import HourlySeries, precipitation_stamp, weather_at
from trips.exceptions import InvalidTrip, QuotaExhausted, UpstreamError
from trips.providers.openmeteo import InvalidForecast, forecast_request, series_for, snap
from trips.providers.osrm import OsrmRouting
from trips.providers.tomtom import TomTomRouting
from trips.providers.types import Place, RawRoute, RoutingProvider

log = logging.getLogger(__name__)

ANALYSIS_TOLERANCE_DEG = 0.0002  # ~20 m: keeps distances exact, drops redundant vertices
DISPLAY_TOLERANCE_DEG = 0.0008  # ~80 m: plenty for the map, a fraction of the payload
CORRIDOR_TOLERANCE_DEG = 0.005
HEATMAP_HOURS = 48
# How far a relayed heatmap start may be from the current hour (clock skew, slow fetches).
HEATMAP_START_SLACK = timedelta(hours=2)
MAX_DEPARTURE_AHEAD = timedelta(days=7)
MAX_DEPARTURE_BEHIND = timedelta(hours=1)
ROUTE_IDS = "ABC"
MAX_AVOID_RECTS = 10  # TomTom's limit per request


@functools.cache
def _timezones() -> TimezoneFinder:
    return TimezoneFinder()


def timezone_at(lat: float, lon: float) -> str:
    return _timezones().timezone_at(lng=lon, lat=lat) or "UTC"


def routing_provider() -> RoutingProvider:
    if settings.TOMTOM_API_KEY:
        return TomTomRouting()
    return OsrmRouting()


# --- track (de)serialisation ------------------------------------------------


def _track_to_store(track: Track) -> dict[str, list]:
    return {
        "points": [[round(lat, 5), round(lon, 5)] for lat, lon in track.points],
        "cum_mi": [round(float(m), 4) for m in track.cum_mi],
        "elapsed_s": [round(float(s), 1) for s in track.elapsed_s],
    }


def _track_from_store(data: dict[str, list]) -> Track:
    return Track(
        [(p[0], p[1]) for p in data["points"]],
        np.asarray(data["cum_mi"], dtype=float),
        np.asarray(data["elapsed_s"], dtype=float),
    )


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


# --- route sets --------------------------------------------------------------


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure_local: datetime
    load_lb: int


@dataclass
class _Route:
    track: Track
    via: str | None
    eta_source: str


def _to_route(raw: RawRoute) -> _Route:
    cum = cumulative_mi(raw.points)
    if cum[-1] > 0:  # align our distances with the provider's, so its offsets line up
        cum = cum * (raw.length_m / METERS_PER_MILE) / cum[-1]
    elapsed, source = build_time_profile(cum, raw.duration_s, raw.progress, raw.instruction_anchors)
    track = Track(raw.points, cum, elapsed).simplified(ANALYSIS_TOLERANCE_DEG)
    return _Route(track, raw.via, source)


def _fetch_routes(
    provider: RoutingProvider, req: TripRequest, departure: datetime, gross_lb: int
) -> tuple[list[_Route], list[str]]:
    origin = (req.origin.lat, req.origin.lon)
    destination = (req.destination.lat, req.destination.lon)
    raws = provider.routes(origin, destination, departure, gross_lb, max_alternatives=2)
    routes: list[_Route] = []
    for raw in raws:
        if len(raw.points) < 2:
            continue
        route = _to_route(raw)
        if routes and distinct_share(route.track, [r.track for r in routes]) < 0.01:
            continue  # exact duplicate
        routes.append(route)
    if not routes:
        raise UpstreamError("No route was found between these places.")

    if len(routes) < 3 and provider.supports_avoid_areas:
        # Block the middle of every route found so far, so the router has to find a genuinely
        # different corridor rather than rediscover one we already have.
        per_route = MAX_AVOID_RECTS // len(routes)
        rects = [rect for r in routes for rect in avoid_rects(r.track, max_rects=per_route)]
        try:
            candidates = provider.routes(
                origin,
                destination,
                departure,
                gross_lb,
                max_alternatives=0,
                avoid=rects,
            )
        except (UpstreamError, QuotaExhausted) as exc:
            log.info("Fallback route request failed: %s", exc)
            candidates = []
        why_not = "no other road connects them without reusing these routes"
        for raw in candidates:
            candidate = _to_route(raw)
            existing = [r.track for r in routes]
            reason = rejection_reason(candidate.track, existing)
            if reason is None and len(routes) < 3:
                routes.append(candidate)
            elif reason is not None:
                fastest = min(existing, key=lambda t: t.duration_s)
                pct = round((detour_ratio(candidate.track, fastest) - 1) * 100)
                if reason.startswith("too"):
                    why_not = f"the best other route is {pct}% longer than the fastest"
                elif reason.startswith("not distinct"):
                    why_not = "the best other route mostly repeats these"
                else:
                    why_not = f"the best other route {reason}"
                log.info("Fallback route rejected: %s (%s%% longer)", reason, pct)

    notes = []
    if len(routes) < 3:
        plural = "route" if len(routes) == 1 else "routes"
        note = f"The routing service found {len(routes)} distinct {plural} for this trip."
        if provider.supports_avoid_areas:
            note += f" A third isn't shown because {why_not}."
        notes.append(note)
    if not provider.truck_aware:
        notes.append(
            "Development routing: no TomTom key is configured, so routes come from OSRM car "
            "routing and ignore truck restrictions. The weather risk rules still use the load."
        )
    routes.sort(key=lambda r: r.track.duration_s)
    return routes[:3], notes


def create_route_set(req: TripRequest, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    origin_tz = timezone_at(req.origin.lat, req.origin.lon)
    try:
        departure = local_to_utc(req.departure_local, origin_tz)
    except NonexistentLocalTime as exc:
        raise InvalidTrip(str(exc), field="departure_local") from exc
    if departure < now - MAX_DEPARTURE_BEHIND:
        raise InvalidTrip(
            "Departure can't be more than an hour in the past.", field="departure_local"
        )
    if departure > now + MAX_DEPARTURE_AHEAD:
        raise InvalidTrip(
            "Departure must be within the next 7 days, the range of the weather forecast.",
            field="departure_local",
        )

    provider = routing_provider()
    gross_lb = req.load_lb + settings.ROUTING_TARE_LB
    rs_id = store.route_set_id(
        {
            "origin": [round(req.origin.lat, 5), round(req.origin.lon, 5)],
            "destination": [round(req.destination.lat, 5), round(req.destination.lon, 5)],
            "departure": _iso(departure),
            "load_lb": req.load_lb,
            "gross_lb": gross_lb,
            "provider": provider.name,
        }
    )
    if (existing := store.find(rs_id)) is not None:
        return existing

    routes, notes = _fetch_routes(provider, req, departure, gross_lb)
    route_set = {
        "id": rs_id,
        "origin": asdict(req.origin),
        "destination": asdict(req.destination),
        "origin_tz": origin_tz,
        "departure_utc": _iso(departure),
        "load_lb": req.load_lb,
        "routing_gross_lb": gross_lb,
        "provider": provider.name,
        "truck_aware": provider.truck_aware,
        "notes": notes,
        "routes": [
            {
                "id": ROUTE_IDS[i],
                "via": r.via,
                "eta_source": r.eta_source,
                "track": _track_to_store(r.track),
            }
            for i, r in enumerate(routes)
        ],
    }
    store.save(route_set)
    return route_set


def route_set_response(route_set: dict[str, Any]) -> dict[str, Any]:
    departure = datetime.fromisoformat(route_set["departure_utc"])
    tracks = {r["id"]: _track_from_store(r["track"]) for r in route_set["routes"]}
    fastest = min(tracks.values(), key=lambda t: t.duration_s)
    routes = []
    for r in route_set["routes"]:
        track = tracks[r["id"]]
        display = track.simplified(DISPLAY_TOLERANCE_DEG)
        ratio = detour_ratio(track, fastest)
        routes.append(
            {
                "id": r["id"],
                "via": r["via"],
                "distance_mi": round(track.total_mi, 1),
                "duration_s": round(track.duration_s),
                "arrival_utc": _iso(departure + timedelta(seconds=track.duration_s)),
                "detour_pct": round((ratio - 1) * 100),
                "long_detour": ratio > LONG_DETOUR_RATIO,
                "eta_source": r["eta_source"],
                "geometry": [[round(a, 5), round(b, 5)] for a, b in display.points],
                "elapsed_s": [round(float(s)) for s in display.elapsed_s],
            }
        )
    keys = (
        "id",
        "origin",
        "destination",
        "origin_tz",
        "departure_utc",
        "load_lb",
        "routing_gross_lb",
        "provider",
        "truck_aware",
        "notes",
    )
    return {**{k: route_set[k] for k in keys}, "routes": routes}


# --- assessment ----------------------------------------------------------------


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _segments(display: Track, checkpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Risk-coloured stretches cut at the attribution boundaries, so the map matches the miles."""
    segments: list[dict[str, Any]] = []
    for cp in checkpoints:
        if cp["to_mi"] <= cp["from_mi"]:
            continue
        piece = slice_between(display.points, display.cum_mi, cp["from_mi"], cp["to_mi"])
        coords = [[round(a, 5), round(b, 5)] for a, b in piece]
        if segments and segments[-1]["level"] == cp["level"]:
            segments[-1]["coords"].extend(coords[1:])
        else:
            segments.append({"level": cp["level"], "coords": coords})
    return segments


def _summary(score: RouteScore) -> dict[str, Any]:
    names = {lvl: lvl.label.lower().replace(" ", "_") for lvl in risk.Risk}
    return {
        "miles_by_level": {names[lvl]: round(m, 1) for lvl, m in score.miles_by_level.items()},
        "unknown_mi": round(score.unknown_mi, 1),
        "coverage": round(score.coverage, 3),
        "risk_index": _round(score.risk_index, 2),
        "max_level": None if score.max_level is None else int(score.max_level),
    }


def _recommendation(rec: Recommendation) -> dict[str, Any]:
    return {
        "status": rec.status,
        "route_id": rec.route_id,
        "explanation": rec.explanation,
        "excluded": [asdict(e) for e in rec.excluded],
        "comparison": [
            {
                "criterion": row.criterion,
                "label": row.label,
                "values": {k: _round(v, 3) for k, v in row.values.items()},
                "decisive": row.decisive,
            }
            for row in rec.comparison
        ],
    }


@dataclass(frozen=True)
class _AssessmentPlan:
    """Checkpoints for every route and the forecast window they need. Deterministic for a route
    set and interval, so the forecast request and the scoring step always agree."""

    route_set: dict[str, Any]
    departure: datetime
    tracks: dict[str, Track]
    slots: dict[str, list[Slot]]
    start: int
    end: int
    locations: list[LatLon]


def _assessment_plan(rs_id: str, interval_mi: int) -> _AssessmentPlan:
    route_set = store.load(rs_id)
    departure = datetime.fromisoformat(route_set["departure_utc"])
    dep_ts = int(departure.timestamp())
    tracks = {r["id"]: _track_from_store(r["track"]) for r in route_set["routes"]}
    slots = {rid: place_checkpoints(track, interval_mi) for rid, track in tracks.items()}
    all_slots = [s for route_slots in slots.values() for s in route_slots]
    return _AssessmentPlan(
        route_set=route_set,
        departure=departure,
        tracks=tracks,
        slots=slots,
        start=floor_hour(dep_ts),
        end=max(precipitation_stamp(dep_ts + round(s.elapsed_s)) for s in all_slots),
        locations=list(dict.fromkeys(snap(s.lat, s.lon) for s in all_slots)),
    )


def _relayed_series(
    locations: list[LatLon], forecasts: list[dict[str, Any] | None]
) -> dict[LatLon, HourlySeries | None]:
    try:
        return series_for(locations, forecasts)
    except InvalidForecast as exc:
        raise InvalidTrip(str(exc), field="forecasts") from exc


def assessment_forecast_request(rs_id: str, interval_mi: int) -> dict[str, Any]:
    plan = _assessment_plan(rs_id, interval_mi)
    return {
        "route_set_id": rs_id,
        "interval_mi": interval_mi,
        "forecast": forecast_request(plan.locations, plan.start, plan.end),
    }


def assess(rs_id: str, interval_mi: int, forecasts: list[dict[str, Any] | None]) -> dict[str, Any]:
    plan = _assessment_plan(rs_id, interval_mi)
    series = _relayed_series(plan.locations, forecasts)
    departure = plan.departure
    load_lb = plan.route_set["load_lb"]
    origin_tz = ZoneInfo(plan.route_set["origin_tz"])

    routes, scores = [], []
    for rid, track in plan.tracks.items():
        checkpoints, scored = [], []
        for slot in plan.slots[rid]:
            eta = departure + timedelta(seconds=round(slot.elapsed_s))
            weather = weather_at(series.get(snap(slot.lat, slot.lon)), int(eta.timestamp()))
            result = risk.assess(weather, load_lb)
            level = None if result.level is None else int(result.level)
            checkpoints.append(
                {
                    "mile": round(slot.mile, 1),
                    "from_mi": round(slot.from_mi, 2),
                    "to_mi": round(slot.to_mi, 2),
                    "lat": round(slot.lat, 5),
                    "lon": round(slot.lon, 5),
                    "eta_utc": _iso(eta),
                    "tz": timezone_at(slot.lat, slot.lon),
                    "wind_mph": None if weather is None else round(weather.wind_mph, 1),
                    "rain_in_hr": None if weather is None else round(weather.rain_in_hr, 3),
                    "snow_in_hr": None if weather is None else round(weather.snow_in_hr, 2),
                    "levels": {
                        "wind": None if result.wind is None else int(result.wind),
                        "rain": None if result.rain is None else int(result.rain),
                        "snow": None if result.snow is None else int(result.snow),
                    },
                    "level": level,
                    "reasons": list(result.reasons),
                }
            )
            scored.append(ScoredCheckpoint(slot.mile, slot.from_mi, slot.to_mi, result.level, eta))
        score = score_route(rid, track.total_mi, track.duration_s, scored)
        scores.append(score)
        routes.append(
            {
                "id": rid,
                "checkpoints": checkpoints,
                "segments": _segments(track.simplified(DISPLAY_TOLERANCE_DEG), checkpoints),
                "summary": _summary(score),
            }
        )

    def format_time(dt: datetime) -> str:
        return dt.astimezone(origin_tz).strftime("%a %H:%M %Z")

    return {
        "route_set_id": rs_id,
        "interval_mi": interval_mi,
        "routes": routes,
        "recommendation": _recommendation(recommend(scores, format_time)),
    }


# --- heatmap -------------------------------------------------------------------


def _corridor(route_set: dict[str, Any]) -> CellGrid:
    corridor = [
        _track_from_store(r["track"]).simplified(CORRIDOR_TOLERANCE_DEG).points
        for r in route_set["routes"]
    ]
    return corridor_grid(
        corridor, buffer_mi=settings.HEATMAP_BUFFER_MI, max_cells=settings.HEATMAP_MAX_CELLS
    )


def heatmap_forecast_request(rs_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Forecasts needed for the corridor cells at forecast hours 0–48 from the current hour."""
    grid = _corridor(store.load(rs_id))
    start = floor_hour(int((now or datetime.now(UTC)).timestamp()))
    end = start + (HEATMAP_HOURS + 1) * HOUR  # the last frame reads the hour after it
    return {
        "route_set_id": rs_id,
        "start_utc": _iso(datetime.fromtimestamp(start, UTC)),
        "forecast": forecast_request(grid.centers, start, end),
    }


def heatmap(
    rs_id: str,
    start_utc: datetime,
    forecasts: list[dict[str, Any] | None],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Risk for each corridor cell at every forecast hour, from relayed forecasts."""
    route_set = store.load(rs_id)
    now = now or datetime.now(UTC)
    start = int(start_utc.timestamp())
    if start % HOUR or abs(start_utc - now) > HEATMAP_START_SLACK:
        raise InvalidTrip("The heatmap start must be a recent whole hour.", field="start_utc")
    grid = _corridor(route_set)
    series = _relayed_series(grid.centers, forecasts)
    load_lb = route_set["load_lb"]
    frames = []
    for h in range(HEATMAP_HOURS + 1):
        ts = start + h * HOUR
        frame = []
        for cell in grid.centers:
            level = risk.assess(weather_at(series.get(cell), ts), load_lb).level
            frame.append(None if level is None else int(level))
        frames.append(frame)
    return {
        "route_set_id": rs_id,
        "start_utc": _iso(datetime.fromtimestamp(start, UTC)),
        "hours": HEATMAP_HOURS + 1,
        "cell_deg": [grid.step_lat, grid.step_lon],
        "cells": [[lat, lon] for lat, lon in grid.centers],
        "risk": frames,
    }
