import math

import pytest

from trips.domain.alternatives import (
    avoid_rects,
    backtrack_mi,
    distinct_share,
    rejection_reason,
)
from trips.domain.corridor import corridor_grid
from trips.domain.geo import MILES_PER_DEG_LAT, LocalProjection

from .helpers import line_points, scaled, straight_track, track_from_points


def test_identical_route_is_not_distinct():
    track = straight_track(200)
    assert distinct_share(track, [track]) == 0.0


def test_parallel_route_five_miles_away_is_distinct():
    assert distinct_share(straight_track(200, lon_offset_mi=5), [straight_track(200)]) == 1.0


def test_half_shared_route():
    base = straight_track(200)
    shared = line_points(100, 51)
    offset_lon = -100.0 + 5 / (MILES_PER_DEG_LAT * math.cos(math.radians(35)))
    detour = [(lat, offset_lon) for lat, _ in line_points(200, 101)[51:]]
    candidate = track_from_points([*shared, *detour])
    assert distinct_share(candidate, [base]) == pytest.approx(0.5, abs=0.05)


def test_backtracking_is_measured():
    assert backtrack_mi(straight_track(200)) == pytest.approx(0, abs=0.01)
    u_turn = track_from_points([(35.0, -100.0), (35.7, -100.0), (35.0, -99.9)])
    assert backtrack_mi(u_turn) > 30


def test_candidate_checks():
    fastest = straight_track(200)
    parallel = straight_track(200, lon_offset_mi=5)
    assert rejection_reason(parallel, [fastest]) is None
    assert (
        rejection_reason(scaled(parallel, 1.5), [fastest])
        == "too slow compared with the fastest route"
    )
    assert rejection_reason(straight_track(300, lon_offset_mi=5), [fastest]).startswith("too")
    assert rejection_reason(fastest, [fastest]) == "not distinct enough from the existing routes"


def test_avoid_rects_cover_the_middle_and_stay_small():
    track = straight_track(1000, n=501)
    rects = avoid_rects(track)
    assert len(rects) == 4
    origin, destination = track.points[0], track.points[-1]
    for r in rects:
        assert (r.north - r.south) * 111 < 160  # km
        assert not (r.south <= origin[0] <= r.north)
        assert not (r.south <= destination[0] <= r.north)


def test_corridor_grid_respects_budget_and_buffer():
    route = line_points(300, 61)
    grid = corridor_grid([route], buffer_mi=30, max_cells=400)
    assert 0 < len(grid.centers) <= 400
    proj = LocalProjection(36.0)
    xy = proj.to_xy(route)
    for lat, lon in grid.centers:
        x, y = proj.to_xy([(lat, lon)])[0]
        nearest = min(math.hypot(x - px, y - py) for px, py in xy)
        assert nearest <= 30 + 3  # within the buffer (sampled route vertices are 5 mi apart)


def test_corridor_grid_is_deterministic_and_on_a_lattice():
    route = line_points(300, 61)
    first = corridor_grid([route])
    assert corridor_grid([route]) == first
    for lat, _ in first.centers:
        assert (lat / first.step_lat - 0.5) == pytest.approx(
            round(lat / first.step_lat - 0.5), abs=1e-6
        )


def test_smaller_budget_means_coarser_cells():
    route = line_points(300, 61)
    fine = corridor_grid([route], max_cells=400)
    coarse = corridor_grid([route], max_cells=50)
    assert len(coarse.centers) <= 50
    assert coarse.step_lat > fine.step_lat


def test_empty_corridor():
    assert corridor_grid([]).centers == []
