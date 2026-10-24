"""Reading an hourly forecast at a truck's ETA.

For the pinned Open-Meteo model, the precipitation value stamped at hour T is the total for the
hour ending at T ("preceding hour sum"), while wind speed at T is instantaneous. So the two are
read differently:

* rain and snow for an ETA come from the hour that contains it (stamp floor(ETA) + 1 h);
* wind speed is interpolated linearly between the surrounding hourly stamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .timeutil import HOUR, floor_hour

Values = tuple[float | None, ...]


@dataclass(frozen=True)
class Weather:
    wind_mph: float
    rain_in_hr: float
    snow_in_hr: float


@dataclass(frozen=True)
class HourlySeries:
    """Hourly forecast for one location. Value k is stamped at `start + k * HOUR`."""

    start: int
    wind_mph: Values
    rain_in: Values  # rain + showers: all liquid precipitation in the hour
    snow_in: Values

    def at(self, values: Values, ts: int) -> float | None:
        offset = ts - self.start
        if offset < 0 or offset % HOUR:
            return None
        k = offset // HOUR
        return values[k] if k < len(values) else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "wind": self.wind_mph,
            "rain": self.rain_in,
            "snow": self.snow_in,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HourlySeries:
        return cls(
            start=data["start"],
            wind_mph=tuple(data["wind"]),
            rain_in=tuple(data["rain"]),
            snow_in=tuple(data["snow"]),
        )


def precipitation_stamp(ts: int) -> int:
    """Stamp of the hourly total covering the hour that contains `ts`."""
    return floor_hour(ts) + HOUR


def wind_at(series: HourlySeries, ts: int) -> float | None:
    t0 = floor_hour(ts)
    w0 = series.at(series.wind_mph, t0)
    if ts == t0:
        return w0
    w1 = series.at(series.wind_mph, t0 + HOUR)
    if w0 is None or w1 is None:
        return None
    return w0 + (w1 - w0) * (ts - t0) / HOUR


def weather_at(series: HourlySeries | None, ts: int) -> Weather | None:
    """Conditions at unix time `ts`, or None when any required value is missing."""
    if series is None:
        return None
    stamp = precipitation_stamp(ts)
    rain = series.at(series.rain_in, stamp)
    snow = series.at(series.snow_in, stamp)
    wind = wind_at(series, ts)
    if rain is None or snow is None or wind is None:
        return None
    return Weather(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow)
