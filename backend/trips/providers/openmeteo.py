"""Open-Meteo hourly forecasts for many locations: cache first, then batched parallel requests."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache

from trips.domain.geo import LatLon
from trips.domain.weather import HourlySeries
from trips.exceptions import UpstreamError

from . import budget
from .http import request

log = logging.getLogger(__name__)

HOURLY = "wind_speed_10m,rain,showers,snowfall"
EXPECTED_UNITS = {"wind_speed_10m": "mp/h", "rain": "inch", "showers": "inch", "snowfall": "inch"}
CM_PER_INCH = 2.54
BATCH_SIZE = 100
WORKERS = 4


def snap(lat: float, lon: float, step: float = 0.05) -> LatLon:
    """Round to a lattice so nearby points (and overlapping routes) share one forecast."""
    return (round(round(lat / step) * step, 4), round(round(lon / step) * step, 4))


def _cache_key(model: str, loc: LatLon, start: int, end: int) -> str:
    return f"wx:{model}:{loc[0]:.4f}:{loc[1]:.4f}:{start}:{end}"


def _iso_hour(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M")


def parse_series(item: dict[str, Any]) -> HourlySeries:
    """One location's response. Units are checked rather than assumed: snowfall in cm is
    converted, anything else unexpected is an error rather than silently skewed results."""
    units = item.get("hourly_units", {})
    snow_factor = 1.0
    for variable, expected in EXPECTED_UNITS.items():
        unit = units.get(variable)
        if variable == "snowfall" and unit == "cm":
            snow_factor = 1 / CM_PER_INCH
        elif unit != expected:
            raise UpstreamError(
                f"Weather service returned {variable} in {unit!r}, expected {expected!r}."
            )
    hourly = item["hourly"]
    rain = tuple(
        None if r is None or s is None else r + s
        for r, s in zip(hourly["rain"], hourly["showers"], strict=True)
    )
    snow = tuple(None if v is None else v * snow_factor for v in hourly["snowfall"])
    return HourlySeries(
        start=int(hourly["time"][0]),
        wind_mph=tuple(hourly["wind_speed_10m"]),
        rain_in=rain,
        snow_in=snow,
    )


class OpenMeteoClient:
    def __init__(self, http: httpx.Client | None = None) -> None:
        self.http = http
        self.model = settings.OPEN_METEO_MODEL
        self.url = settings.OPEN_METEO_URL

    def fetch(
        self, locations: Iterable[LatLon], start: int, end: int
    ) -> dict[LatLon, HourlySeries | None]:
        """Hourly series covering [start, end] for each location. A location whose request
        failed maps to None, which the risk logic treats as unknown, never as Low."""
        unique = list(dict.fromkeys(locations))
        keys = {loc: _cache_key(self.model, loc, start, end) for loc in unique}
        cached = cache.get_many(list(keys.values()))  # one MGET on Redis
        result: dict[LatLon, HourlySeries | None] = {}
        missing = []
        for loc in unique:
            hit = cached.get(keys[loc])
            if hit is None:
                missing.append(loc)
            else:
                result[loc] = HourlySeries.from_dict(hit)
        if not missing:
            return result

        budget.consume("open_meteo", len(missing))
        batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(batches))) as pool:
            fetched = pool.map(lambda batch: self._fetch_batch(batch, start, end), batches)
            for batch, series in zip(batches, fetched, strict=True):
                result.update(zip(batch, series, strict=True))

        fresh = {keys[loc]: result[loc].to_dict() for loc in missing if result[loc] is not None}
        if fresh:
            cache.set_many(fresh, timeout=settings.WEATHER_TTL_S)
        return result

    def _fetch_batch(self, batch: list[LatLon], start: int, end: int) -> list[HourlySeries | None]:
        params = {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in batch),
            "hourly": HOURLY,
            "models": self.model,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timeformat": "unixtime",
            "timezone": "GMT",
            "start_hour": _iso_hour(start),
            "end_hour": _iso_hour(end),
        }
        try:
            response = request("GET", self.url, params=params, http=self.http)
        except httpx.HTTPError as exc:
            log.warning("Open-Meteo request failed: %s", exc)
            return [None] * len(batch)
        if response.status_code != 200:
            log.warning("Open-Meteo returned %s: %s", response.status_code, response.text[:200])
            return [None] * len(batch)
        data = response.json()
        items = data if isinstance(data, list) else [data]
        if len(items) != len(batch):
            log.warning("Open-Meteo returned %d locations for %d requested", len(items), len(batch))
            return [None] * len(batch)
        return [parse_series(item) for item in items]
