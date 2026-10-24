"""Route summaries and the recommendation.

Eligibility comes first: a route can be recommended only if every checkpoint has a forecast
(unknown weather must never make a route look safer) and it has no No Travel miles. Among
eligible routes the brief's order applies exactly:

    1. fewest Severe miles  2. fewest High miles  3. lowest risk index  4. shortest travel time

The risk index is the distance-weighted mean of the ordinal levels (Low = 0 … No Travel = 4). It
ranks routes; it is not a probability.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from .risk import Risk
from .text import format_duration, format_miles

Status = Literal["recommended", "no_safe_route", "insufficient_data"]
Criterion = Literal["no_travel_mi", "coverage", "severe_mi", "high_mi", "risk_index", "duration_s"]

RANKED: tuple[Criterion, ...] = ("severe_mi", "high_mi", "risk_index", "duration_s")
CRITERIA: tuple[tuple[Criterion, str], ...] = (
    ("no_travel_mi", "No Travel miles"),
    ("coverage", "Weather coverage"),
    ("severe_mi", "Severe miles"),
    ("high_mi", "High miles"),
    ("risk_index", "Risk index (0–4)"),
    ("duration_s", "Travel time"),
)


@dataclass(frozen=True)
class ScoredCheckpoint:
    mile: float
    from_mi: float
    to_mi: float
    level: Risk | None
    eta: datetime


@dataclass(frozen=True)
class RouteScore:
    route_id: str
    distance_mi: float
    duration_s: float
    miles_by_level: dict[Risk, float]
    unknown_mi: float
    risk_index: float | None
    max_level: Risk | None
    first_no_travel: ScoredCheckpoint | None

    @property
    def severe_mi(self) -> float:
        return self.miles_by_level[Risk.SEVERE]

    @property
    def high_mi(self) -> float:
        return self.miles_by_level[Risk.HIGH]

    @property
    def no_travel_mi(self) -> float:
        return self.miles_by_level[Risk.NO_TRAVEL]

    @property
    def complete(self) -> bool:
        return self.unknown_mi <= 1e-9

    @property
    def coverage(self) -> float:
        if self.distance_mi <= 0:
            return 1.0 if self.complete else 0.0
        return max(0.0, 1 - self.unknown_mi / self.distance_mi)

    def value(self, criterion: Criterion) -> float | None:
        return getattr(self, criterion)


def score_route(
    route_id: str, distance_mi: float, duration_s: float, checkpoints: Sequence[ScoredCheckpoint]
) -> RouteScore:
    miles = dict.fromkeys(Risk, 0.0)
    unknown = 0.0
    for cp in checkpoints:
        span = cp.to_mi - cp.from_mi
        if cp.level is None:
            unknown += span
        else:
            miles[cp.level] += span
    known = sum(miles.values())
    risk_index = sum(level * m for level, m in miles.items()) / known if known > 0 else None
    levels = [cp.level for cp in checkpoints if cp.level is not None]
    return RouteScore(
        route_id=route_id,
        distance_mi=distance_mi,
        duration_s=duration_s,
        miles_by_level=miles,
        unknown_mi=unknown,
        risk_index=risk_index,
        max_level=max(levels) if levels else None,
        first_no_travel=next((cp for cp in checkpoints if cp.level == Risk.NO_TRAVEL), None),
    )


def _rounded(score: RouteScore, criterion: Criterion) -> float:
    """Comparison value, rounded so floating-point noise never decides a tie."""
    value = score.value(criterion)
    if value is None:
        return float("inf")
    digits = {"risk_index": 2, "coverage": 3, "duration_s": 0}.get(criterion, 1)
    return round(value, digits)


def pdf_key(score: RouteScore) -> tuple:
    return (*(_rounded(score, c) for c in RANKED), score.route_id)


@dataclass(frozen=True)
class Exclusion:
    route_id: str
    reason: Literal["incomplete", "no_travel"]
    detail: str


@dataclass(frozen=True)
class ComparisonRow:
    criterion: Criterion
    label: str
    values: dict[str, float | None]
    decisive: bool


@dataclass(frozen=True)
class Recommendation:
    status: Status
    route_id: str | None
    explanation: str
    excluded: list[Exclusion] = field(default_factory=list)
    comparison: list[ComparisonRow] = field(default_factory=list)


def _exclusion(score: RouteScore, format_time: Callable[[datetime], str]) -> Exclusion | None:
    if not score.complete:
        missing = round((1 - score.coverage) * 100)
        return Exclusion(
            score.route_id,
            "incomplete",
            f"Route {score.route_id}: no forecast for {max(missing, 1)}% of the route, "
            "so it can't be fully assessed.",
        )
    if score.no_travel_mi > 0 and score.first_no_travel is not None:
        cp = score.first_no_travel
        return Exclusion(
            score.route_id,
            "no_travel",
            f"Route {score.route_id}: No Travel conditions at mile {cp.mile:,.0f} "
            f"({format_time(cp.eta)}).",
        )
    return None


def _routes(scores: Sequence[RouteScore]) -> str:
    """ "Route A", "Routes A and B", "Routes A, B and C"."""
    ids = [s.route_id for s in scores]
    if len(ids) == 1:
        return f"Route {ids[0]}"
    return f"Routes {', '.join(ids[:-1])} and {ids[-1]}"


def _first_difference(
    a: RouteScore, b: RouteScore, criteria: Sequence[Criterion]
) -> Criterion | None:
    return next((c for c in criteria if _rounded(a, c) != _rounded(b, c)), None)


def _ranked_reason(pick: RouteScore, other: RouteScore, criterion: Criterion | None) -> str:
    p, o = pick.route_id, other.route_id
    match criterion:
        case "severe_mi":
            return (
                f"it has the fewest Severe miles ({format_miles(pick.severe_mi)} vs "
                f"{format_miles(other.severe_mi)} on Route {o})"
            )
        case "high_mi":
            return (
                f"it ties Route {o} on Severe miles and has fewer High miles "
                f"({format_miles(pick.high_mi)} vs {format_miles(other.high_mi)})"
            )
        case "risk_index":
            return (
                f"it ties Route {o} on Severe and High miles and has a lower risk index "
                f"({pick.risk_index:.2f} vs {other.risk_index:.2f})"
            )
        case "duration_s":
            return (
                f"it ties Route {o} on every risk measure and is faster "
                f"({format_duration(pick.duration_s)} vs {format_duration(other.duration_s)})"
            )
        case _:
            return (
                f"Routes {p} and {o} are identical on every criterion, "
                "so the first listed is chosen"
            )


def recommend(
    scores: Sequence[RouteScore], format_time: Callable[[datetime], str]
) -> Recommendation:
    exclusions = {s.route_id: _exclusion(s, format_time) for s in scores}
    eligible = sorted((s for s in scores if exclusions[s.route_id] is None), key=pdf_key)
    complete = [s for s in scores if s.complete]
    excluded = [e for e in exclusions.values() if e is not None]
    decisive: set[Criterion] = set()

    if eligible:
        status: Status = "recommended"
        pick = eligible[0]
        if len(eligible) >= 2:
            criterion = _first_difference(pick, eligible[1], RANKED)
            decisive = {criterion} if criterion else set()
            reason = _ranked_reason(pick, eligible[1], criterion)
            explanation = f"Route {pick.route_id} is recommended: {reason}."
        elif excluded:
            reasons = {e.reason for e in excluded}
            decisive = {"no_travel_mi" if r == "no_travel" else "coverage" for r in reasons}
            parts = []
            if "incomplete" in reasons:
                parts.append("complete forecasts")
            if "no_travel" in reasons:
                parts.append("no No Travel conditions")
            explanation = (
                f"Route {pick.route_id} is recommended: it is the only route with "
                f"{' and '.join(parts)}."
            )
        else:
            explanation = (
                f"Route {pick.route_id} is recommended: it has complete forecasts and no "
                "No Travel conditions."
            )
        fastest = min(scores, key=lambda s: (round(s.duration_s), s.route_id))
        if fastest.route_id != pick.route_id:
            explanation += (
                f" It takes {format_duration(pick.duration_s - fastest.duration_s)} longer than "
                f"the fastest route (Route {fastest.route_id})."
            )
    elif complete:
        # Every fully forecast route has No Travel miles; any others lack complete forecasts.
        status = "no_safe_route"
        incomplete = [s for s in scores if not s.complete]
        ranked = sorted(complete, key=lambda s: (_rounded(s, "no_travel_mi"), *pdf_key(s)))
        pick = ranked[0]
        if len(ranked) >= 2:
            criterion = _first_difference(pick, ranked[1], ("no_travel_mi", *RANKED))
            decisive = {criterion} if criterion else set()
        elif incomplete:
            decisive = {"coverage"}
        no_travel = format_miles(pick.no_travel_mi)
        if incomplete:
            explanation = (
                f"No route is safe at this departure time: {_routes(complete)} "
                f"{'has' if len(complete) == 1 else 'have'} No Travel conditions, and "
                f"{_routes(incomplete)} {'lacks' if len(incomplete) == 1 else 'lack'} "
                f"complete forecasts. Route {pick.route_id} is the least risky fully forecast "
                f"option ({no_travel} of No Travel), but it is not recommended."
            )
        else:
            explanation = (
                "No route is safe at this departure time: every route has No Travel "
                f"conditions. Route {pick.route_id} is the least risky option ({no_travel} of "
                "No Travel), but it is not recommended."
            )
    else:
        status = "insufficient_data"
        pick = None
        decisive = {"coverage"}
        explanation = (
            "Weather forecasts are unavailable for parts of every route, so no route can be "
            "recommended."
        )

    comparison = [
        ComparisonRow(
            criterion=c,
            label=label,
            values={s.route_id: s.value(c) for s in scores},
            decisive=c in decisive,
        )
        for c, label in CRITERIA
    ]
    return Recommendation(
        status=status,
        route_id=pick.route_id if pick else None,
        explanation=explanation,
        excluded=excluded,
        comparison=comparison,
    )
