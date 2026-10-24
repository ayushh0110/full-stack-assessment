from datetime import datetime

import pytest

from trips.domain.timeutil import (
    HOUR,
    NonexistentLocalTime,
    ceil_hour,
    floor_hour,
    local_to_utc,
)
from trips.domain.weather import HourlySeries, precipitation_stamp, weather_at

T0 = 1_800_000_000 - 1_800_000_000 % HOUR

SERIES = HourlySeries(
    start=T0,
    wind_mph=(10.0, 20.0, 30.0, None),
    rain_in=(0.0, 0.1, 0.2, 0.3),
    snow_in=(0.0, 0.0, 0.5, None),
)


@pytest.mark.parametrize("offset", [0, 20 * 60, HOUR - 1])
def test_precipitation_comes_from_the_hour_containing_the_eta(offset):
    # 14:00, 14:20 and 14:59 all read the total stamped 15:00 (the 14:00–15:00 hour).
    assert precipitation_stamp(T0 + offset) == T0 + HOUR


def test_wind_is_interpolated_between_hourly_stamps():
    result = weather_at(SERIES, T0 + 20 * 60)
    assert result is not None
    assert result.wind_mph == pytest.approx(10 + 10 / 3)
    assert result.rain_in_hr == 0.1
    assert result.snow_in_hr == 0.0


def test_on_the_hour_uses_that_stamp_for_wind():
    result = weather_at(SERIES, T0 + HOUR)
    assert result is not None
    assert result.wind_mph == 20.0
    assert result.rain_in_hr == 0.2
    assert result.snow_in_hr == 0.5


def test_missing_value_makes_weather_unknown():
    assert weather_at(SERIES, T0 + 2 * HOUR + 1800) is None  # wind at T0+3h is missing


def test_outside_the_series_is_unknown():
    assert weather_at(SERIES, T0 - 1) is None
    assert weather_at(SERIES, T0 + 10 * HOUR) is None
    assert weather_at(None, T0) is None


def test_series_round_trips_through_cache_format():
    assert HourlySeries.from_dict(SERIES.to_dict()) == SERIES


def test_local_time_converts_with_daylight_saving():
    summer = local_to_utc(datetime(2026, 7, 1, 7, 0), "America/Denver")
    winter = local_to_utc(datetime(2026, 12, 1, 7, 0), "America/Denver")
    assert summer.isoformat() == "2026-07-01T13:00:00+00:00"  # MDT, UTC-6
    assert winter.isoformat() == "2026-12-01T14:00:00+00:00"  # MST, UTC-7


def test_spring_forward_gap_is_rejected():
    with pytest.raises(NonexistentLocalTime):
        local_to_utc(datetime(2026, 3, 8, 2, 30), "America/Denver")


def test_fall_back_ambiguity_takes_earlier_occurrence():
    result = local_to_utc(datetime(2026, 11, 1, 1, 30), "America/Denver")
    assert result.isoformat() == "2026-11-01T07:30:00+00:00"  # still MDT


def test_aware_input_is_rejected():
    with pytest.raises(ValueError):
        local_to_utc(datetime.fromisoformat("2026-07-01T07:00:00+00:00"), "America/Denver")


def test_hour_rounding():
    assert floor_hour(T0 + 59) == T0
    assert ceil_hour(T0 + 59) == T0 + HOUR
    assert ceil_hour(T0) == T0
