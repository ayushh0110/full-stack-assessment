import pytest

from trips.domain.risk import (
    Risk,
    apply_load_rules,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
)
from trips.domain.weather import Weather

L, M, H, S, NT = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


@pytest.mark.parametrize(
    ("mph", "expected"),
    [
        (0, L),
        (24.9, L),
        (25, M),
        (34.9, M),
        (35, H),
        (44.9, H),
        (45, S),
        (54.9, S),
        (55, NT),
        (90, NT),
    ],
)
def test_wind_thresholds(mph, expected):
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    ("in_hr", "expected"),
    [
        (0, L),
        (0.099, L),
        (0.10, M),
        (0.249, M),
        (0.25, H),  # 0.25 appears in both Moderate and High ranges: lower bound wins
        (0.499, H),
        (0.50, S),
        (1.00, S),  # No Travel is strictly > 1.00
        (1.001, NT),
    ],
)
def test_rain_thresholds(in_hr, expected):
    assert classify_rain(in_hr) == expected


@pytest.mark.parametrize(
    ("in_hr", "expected"),
    [(0, L), (0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H), (2.0, S), (3.0, S), (3.01, NT)],
)
def test_snow_thresholds(in_hr, expected):
    assert classify_snow(in_hr) == expected


@pytest.mark.parametrize(
    ("mph", "load_lb", "expected"),
    [
        (55, 0, NT),  # >= 55 mph: No Travel for any load
        (60, 10_000, NT),
        (50, 30_000, S),  # exactly 30,000 is not > 30,000
        (50, 30_001, NT),
        (45, 30_001, NT),
        (54.9, 45_000, NT),
        (44.9, 40_000, H),  # exactly 40,000 is not > 40,000
        (44.9, 40_001, S),
        (35, 40_001, S),
        (34.9, 40_001, M),  # below the 35–44 band: no escalation
        (40, 35_000, H),  # the 30,000 rule applies only at 45–54 mph
        (20, 80_000, L),
    ],
)
def test_load_rules(mph, load_lb, expected):
    assert apply_load_rules(mph, classify_wind(mph), load_lb) == expected


def test_unknown_weather_is_never_low():
    result = assess(None, 20_000)
    assert result.level is None
    assert result.reasons == ("Forecast unavailable",)


def test_overall_level_is_worst_factor():
    result = assess(Weather(wind_mph=30, rain_in_hr=0.30, snow_in_hr=0.0), 20_000)
    assert (result.wind, result.rain, result.snow) == (M, H, L)
    assert result.level == H
    assert result.reasons == ("Wind 30.0 mph → Moderate", "Rain 0.30 in/hr → High")


def test_load_escalation_is_explained():
    result = assess(Weather(wind_mph=47, rain_in_hr=0, snow_in_hr=0), 42_000)
    assert result.level == NT
    assert "load rule" in result.reasons[0]
    assert "42,000 lb" in result.reasons[0]


def test_all_low_reason():
    result = assess(Weather(wind_mph=5, rain_in_hr=0, snow_in_hr=0), 10_000)
    assert result.level == L
    assert result.reasons == ("Wind, rain and snow all Low",)
