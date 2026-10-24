"""Local-time conversion and hourly time arithmetic."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

HOUR = 3600


class NonexistentLocalTime(ValueError):
    """The wall-clock time falls in a daylight-saving gap (clocks skip forward)."""


def local_to_utc(local: datetime, tz_name: str) -> datetime:
    """Interpret a naive wall-clock time in `tz_name` and convert it to UTC.

    Ambiguous times (clocks fall back) resolve to the earlier occurrence. Times skipped by a
    spring-forward change do not exist and are rejected.
    """
    if local.tzinfo is not None:
        raise ValueError("expected a naive local time")
    tz = ZoneInfo(tz_name)
    as_utc = local.replace(tzinfo=tz, fold=0).astimezone(UTC)
    if as_utc.astimezone(tz).replace(tzinfo=None) != local:
        raise NonexistentLocalTime(
            f"{local:%Y-%m-%d %H:%M} does not exist in {tz_name} (clocks skip forward)."
        )
    return as_utc


def floor_hour(ts: int) -> int:
    return ts - ts % HOUR


def ceil_hour(ts: int) -> int:
    return ts if ts % HOUR == 0 else floor_hour(ts) + HOUR
