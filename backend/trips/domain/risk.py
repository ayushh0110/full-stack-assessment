"""Weather risk classification, implementing the brief's risk and load rules.

Threshold edges: the brief's ranges touch or overlap (rain 0.10–0.25 and 0.25–0.50, wind 34 vs
35), so each lower bound is inclusive. Rain and snow "Severe" include their upper bound because
No Travel is strictly greater than it.

    Condition   Low        Moderate     High         Severe       No Travel
    Wind (mph)  < 25       [25, 35)     [35, 45)     [45, 55)     >= 55
    Rain (in/h) < 0.10     [0.10,0.25)  [0.25,0.50)  [0.50,1.00]  > 1.00
    Snow (in/h) < 0.5      [0.5, 1.0)   [1.0, 2.0)   [2.0, 3.0]   > 3.0

Load rules (strictly greater than; they can only raise the wind level):
    wind >= 55 mph                    -> No Travel for any load
    wind 45–54 mph and load > 30,000  -> No Travel
    wind 35–44 mph and load > 40,000  -> Severe
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .weather import Weather


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return LABELS[self]


LABELS = {
    Risk.LOW: "Low",
    Risk.MODERATE: "Moderate",
    Risk.HIGH: "High",
    Risk.SEVERE: "Severe",
    Risk.NO_TRAVEL: "No Travel",
}


def classify_wind(mph: float) -> Risk:
    if mph >= 55:
        return Risk.NO_TRAVEL
    if mph >= 45:
        return Risk.SEVERE
    if mph >= 35:
        return Risk.HIGH
    if mph >= 25:
        return Risk.MODERATE
    return Risk.LOW


def classify_rain(in_hr: float) -> Risk:
    if in_hr > 1.00:
        return Risk.NO_TRAVEL
    if in_hr >= 0.50:
        return Risk.SEVERE
    if in_hr >= 0.25:
        return Risk.HIGH
    if in_hr >= 0.10:
        return Risk.MODERATE
    return Risk.LOW


def classify_snow(in_hr: float) -> Risk:
    if in_hr > 3.0:
        return Risk.NO_TRAVEL
    if in_hr >= 2.0:
        return Risk.SEVERE
    if in_hr >= 1.0:
        return Risk.HIGH
    if in_hr >= 0.5:
        return Risk.MODERATE
    return Risk.LOW


def apply_load_rules(mph: float, level: Risk, load_lb: float) -> Risk:
    if mph >= 55:
        return Risk.NO_TRAVEL
    if 45 <= mph < 55 and load_lb > 30_000:
        return Risk.NO_TRAVEL
    if 35 <= mph < 45 and load_lb > 40_000:
        return max(level, Risk.SEVERE)
    return level


@dataclass(frozen=True)
class Assessment:
    """Risk at one place and time. `level` is None when the forecast is unavailable — unknown is
    never treated as Low."""

    level: Risk | None
    wind: Risk | None = None
    rain: Risk | None = None
    snow: Risk | None = None
    reasons: tuple[str, ...] = ()


UNKNOWN = Assessment(level=None, reasons=("Forecast unavailable",))


def assess(weather: Weather | None, load_lb: float) -> Assessment:
    if weather is None:
        return UNKNOWN
    base_wind = classify_wind(weather.wind_mph)
    wind = apply_load_rules(weather.wind_mph, base_wind, load_lb)
    rain = classify_rain(weather.rain_in_hr)
    snow = classify_snow(weather.snow_in_hr)

    reasons: list[str] = []
    if wind > base_wind:
        reasons.append(
            f"Wind {weather.wind_mph:.1f} mph with a {load_lb:,.0f} lb load"
            f" → {wind.label} (load rule)"
        )
    elif wind > Risk.LOW:
        reasons.append(f"Wind {weather.wind_mph:.1f} mph → {wind.label}")
    if rain > Risk.LOW:
        reasons.append(f"Rain {weather.rain_in_hr:.2f} in/hr → {rain.label}")
    if snow > Risk.LOW:
        reasons.append(f"Snow {weather.snow_in_hr:.2f} in/hr → {snow.label}")
    if not reasons:
        reasons.append("Wind, rain and snow all Low")

    return Assessment(
        level=max(wind, rain, snow), wind=wind, rain=rain, snow=snow, reasons=tuple(reasons)
    )
