"""Formatting for user-facing explanation text."""


def format_duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    hours, mins = divmod(minutes, 60)
    if hours == 0:
        return f"{mins} m"
    return f"{hours} h {mins:02d} m"


def format_miles(miles: float) -> str:
    return f"{miles:,.0f} mi" if miles >= 10 or miles == 0 else f"{miles:.1f} mi"
