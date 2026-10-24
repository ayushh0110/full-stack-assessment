"""Open-Meteo hourly forecasts, fetched by the visitor's browser and validated here.

Open-Meteo's free tier is limited per IP address, and shared hosting IPs (such as Render's free
plan) run out of quota because of other tenants. So the server describes exactly what to fetch
(`forecast_request`), the browser fetches it with the visitor's own quota, and the server checks
and interprets every relayed response (`series_for`). All risk logic stays on the server.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from django.conf import settings

from trips.domain.geo import LatLon
from trips.domain.timeutil import HOUR
from trips.domain.weather import HourlySeries

HOURLY = "wind_speed_10m,rain,showers,snowfall"
# Units exactly as Open-Meteo labels them in "hourly_units" (it spells miles per hour "mp/h").
EXPECTED_UNITS = {"wind_speed_10m": "mp/h", "rain": "inch", "showers": "inch", "snowfall": "inch"}
CM_PER_INCH = 2.54
BATCH_SIZE = 100
# A returned grid point further than this from the requested location is not trusted.
MAX_LOCATION_DRIFT_DEG = 0.3


class InvalidForecast(ValueError):
    """A relayed forecast is malformed, in unexpected units, or doesn't match the request."""


def snap(lat: float, lon: float, step: float = 0.05) -> LatLon:
    """Round to a lattice so nearby points (and overlapping routes) share one forecast."""
    return (round(round(lat / step) * step, 4), round(round(lon / step) * step, 4))


def _iso_hour(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M")


def forecast_request(locations: Sequence[LatLon], start: int, end: int) -> dict[str, Any]:
    """Everything the browser needs to fetch forecasts for `locations` over [start, end]."""
    return {
        "url": settings.OPEN_METEO_URL,
        "params": {
            "hourly": HOURLY,
            "models": settings.OPEN_METEO_MODEL,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timeformat": "unixtime",
            "timezone": "GMT",
            "start_hour": _iso_hour(start),
            "end_hour": _iso_hour(end),
        },
        "batch_size": BATCH_SIZE,
        "locations": [[lat, lon] for lat, lon in locations],
    }


def _values(hourly: dict[str, Any], key: str, length: int) -> tuple[float | None, ...]:
    values = hourly.get(key)
    if not isinstance(values, list) or len(values) != length:
        raise InvalidForecast(f"Forecast field {key!r} is missing or has the wrong length.")
    if not all(
        v is None or (isinstance(v, int | float) and not isinstance(v, bool)) for v in values
    ):
        raise InvalidForecast(f"Forecast field {key!r} must contain numbers.")
    return tuple(None if v is None else float(v) for v in values)


def parse_series(item: dict[str, Any]) -> HourlySeries:
    """One location's Open-Meteo response. Units are checked rather than assumed: snowfall in cm
    is converted, anything else unexpected is rejected rather than silently skewing results."""
    if not isinstance(item, dict) or not isinstance(item.get("hourly"), dict):
        raise InvalidForecast("Each forecast must be an Open-Meteo location object.")
    units = item.get("hourly_units") or {}
    snow_factor = 1.0
    for variable, expected in EXPECTED_UNITS.items():
        unit = units.get(variable)
        if variable == "snowfall" and unit == "cm":
            snow_factor = 1 / CM_PER_INCH
        elif unit != expected:
            raise InvalidForecast(f"Forecast {variable} is in {unit!r}, expected {expected!r}.")
    hourly = item["hourly"]
    times = hourly.get("time")
    if not isinstance(times, list) or not times or not all(isinstance(t, int) for t in times):
        raise InvalidForecast("Forecast times must be unix timestamps.")
    if any(b - a != HOUR for a, b in pairwise(times)):
        raise InvalidForecast("Forecast times must be hourly.")
    n = len(times)
    rain, showers = _values(hourly, "rain", n), _values(hourly, "showers", n)
    snow = _values(hourly, "snowfall", n)
    return HourlySeries(
        start=times[0],
        wind_mph=_values(hourly, "wind_speed_10m", n),
        rain_in=tuple(
            None if r is None or s is None else r + s for r, s in zip(rain, showers, strict=True)
        ),
        snow_in=tuple(None if v is None else v * snow_factor for v in snow),
    )


def series_for(
    locations: Sequence[LatLon], forecasts: Sequence[dict[str, Any] | None]
) -> dict[LatLon, HourlySeries | None]:
    """Match relayed forecasts to the requested locations, in order. A missing (null) forecast,
    or one for a different place, maps to None: unknown weather, never treated as Low."""
    if len(forecasts) != len(locations):
        raise InvalidForecast(
            f"Expected one forecast per requested location ({len(locations)}), "
            f"got {len(forecasts)}."
        )
    result: dict[LatLon, HourlySeries | None] = {}
    for (lat, lon), item in zip(locations, forecasts, strict=True):
        if item is None:
            result[(lat, lon)] = None
            continue
        series = parse_series(item)
        got_lat, got_lon = item.get("latitude"), item.get("longitude")
        drifted = (
            isinstance(got_lat, int | float)
            and isinstance(got_lon, int | float)
            and (
                abs(got_lat - lat) > MAX_LOCATION_DRIFT_DEG
                or abs(got_lon - lon) > MAX_LOCATION_DRIFT_DEG
            )
        )
        result[(lat, lon)] = None if drifted else series
    return result
