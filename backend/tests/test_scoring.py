from datetime import UTC, datetime

import pytest

from trips.domain.risk import Risk
from trips.domain.scoring import ScoredCheckpoint, recommend, score_route

L, M, H, S, NT = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL
ETA = datetime(2026, 10, 25, 14, 20, tzinfo=UTC)


def fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def route(route_id: str, stretches, duration_s: float = 36_000):
    """Build a scored route from consecutive (miles, level) stretches."""
    checkpoints, pos = [], 0.0
    for span, level in stretches:
        checkpoints.append(ScoredCheckpoint(pos + span / 2, pos, pos + span, level, ETA))
        pos += span
    return score_route(route_id, pos, duration_s, checkpoints)


def test_summary_counts_attributed_miles():
    score = route("A", [(50, L), (25, H), (25, H)])
    assert score.miles_by_level[H] == 50
    assert score.risk_index == pytest.approx(1.0)
    assert score.max_level == H
    assert score.coverage == 1.0


def test_unknown_miles_are_tracked_not_scored_as_low():
    score = route("A", [(850, L), (150, None)])
    assert score.unknown_mi == 150
    assert score.coverage == pytest.approx(0.85)
    assert score.risk_index == 0  # over known miles only
    assert not score.complete


def test_missing_weather_cannot_win():
    a = route("A", [(10, S), (840, L), (150, None)])  # fewer Severe miles, but 150 unseen
    b = route("B", [(15, S), (985, L)])
    rec = recommend([a, b], fmt)
    assert rec.status == "recommended"
    assert rec.route_id == "B"
    assert [(e.route_id, e.reason) for e in rec.excluded] == [("A", "incomplete")]


def test_fewest_severe_miles_wins_first():
    a = route("A", [(100, L), (50, H)], duration_s=40_000)
    b = route("B", [(125, L), (25, S)], duration_s=30_000)
    rec = recommend([a, b], fmt)
    assert rec.route_id == "A"
    assert "fewest Severe miles" in rec.explanation
    assert "longer than the fastest route (Route B)" in rec.explanation
    assert [r.criterion for r in rec.comparison if r.decisive] == ["severe_mi"]


def test_high_miles_break_a_severe_tie():
    a = route("A", [(90, L), (10, H)], duration_s=40_000)
    b = route("B", [(70, L), (30, H)], duration_s=30_000)
    assert recommend([a, b], fmt).route_id == "A"


def test_risk_index_breaks_a_severe_and_high_tie():
    a = route("A", [(60, L), (40, M)], duration_s=30_000)
    b = route("B", [(90, L), (10, M)], duration_s=40_000)
    rec = recommend([a, b], fmt)
    assert rec.route_id == "B"
    assert "lower risk index" in rec.explanation


def test_travel_time_breaks_a_full_risk_tie():
    a = route("A", [(100, L)], duration_s=40_000)
    b = route("B", [(100, L)], duration_s=30_000)
    rec = recommend([a, b], fmt)
    assert rec.route_id == "B"
    assert [r.criterion for r in rec.comparison if r.decisive] == ["duration_s"]


def test_identical_routes_pick_deterministically():
    a = route("A", [(100, L)])
    b = route("B", [(100, L)])
    rec = recommend([b, a], fmt)
    assert rec.route_id == "A"
    assert "identical" in rec.explanation


def test_no_travel_is_an_eligibility_gate():
    a = route("A", [(90, L), (10, NT)])  # zero Severe miles but No Travel
    b = route("B", [(50, L), (50, S)])
    rec = recommend([a, b], fmt)
    assert rec.status == "recommended"
    assert rec.route_id == "B"
    assert rec.excluded[0].reason == "no_travel"
    assert "mile 95 (14:20)" in rec.excluded[0].detail
    assert "only route with no No Travel conditions" in rec.explanation


def test_all_routes_no_travel():
    a = route("A", [(90, L), (10, NT)])
    b = route("B", [(70, L), (30, NT)])
    rec = recommend([a, b], fmt)
    assert rec.status == "no_safe_route"
    assert rec.route_id == "A"
    assert "not recommended" in rec.explanation
    assert "every route has No Travel conditions" in rec.explanation


def test_no_travel_on_one_route_and_missing_forecasts_on_the_other():
    a = route("A", [(90, L), (10, NT)])
    b = route("B", [(90, L), (10, None)])  # no No Travel, but incomplete
    rec = recommend([a, b], fmt)
    assert rec.status == "no_safe_route"
    assert rec.route_id == "A"
    assert "every route has No Travel" not in rec.explanation
    assert rec.explanation == (
        "No route is safe at this departure time: Route A has No Travel conditions, and "
        "Route B lacks complete forecasts. Route A is the least risky fully forecast option "
        "(10 mi of No Travel), but it is not recommended."
    )
    assert [r.criterion for r in rec.comparison if r.decisive] == ["coverage"]


def test_no_safe_route_wording_with_several_routes_in_each_group():
    routes = [
        route("A", [(90, L), (10, NT)]),
        route("B", [(80, L), (20, NT)]),
        route("C", [(90, L), (10, None)]),
    ]
    rec = recommend(routes, fmt)
    assert "Routes A and B have No Travel conditions, and Route C lacks" in rec.explanation


def test_all_routes_incomplete():
    a = route("A", [(90, L), (10, None)])
    b = route("B", [(90, L), (10, None)])
    rec = recommend([a, b], fmt)
    assert rec.status == "insufficient_data"
    assert rec.route_id is None


def test_comparison_lists_every_criterion_for_every_route():
    a = route("A", [(100, L)])
    b = route("B", [(100, M)])
    rec = recommend([a, b], fmt)
    assert [r.criterion for r in rec.comparison] == [
        "no_travel_mi",
        "coverage",
        "severe_mi",
        "high_mi",
        "risk_index",
        "duration_s",
    ]
    assert all(set(r.values) == {"A", "B"} for r in rec.comparison)
