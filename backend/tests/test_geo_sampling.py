import numpy as np
import pytest

from trips.domain.geo import (
    cumulative_mi,
    haversine_mi,
    point_at,
    simplify_indices,
    slice_between,
)
from trips.domain.sampling import (
    attribution_bounds,
    build_time_profile,
    checkpoint_miles,
    place_checkpoints,
)

from .helpers import straight_track


def test_haversine_denver_to_chicago():
    assert haversine_mi((39.7392, -104.9903), (41.8781, -87.6298)) == pytest.approx(920, rel=0.01)


def test_cumulative_distance_matches_segment_sum():
    points = [(35.0, -100.0), (35.5, -100.0), (35.5, -99.0)]
    cum = cumulative_mi(points)
    assert cum[0] == 0
    assert cum[-1] == pytest.approx(
        haversine_mi(points[0], points[1]) + haversine_mi(points[1], points[2])
    )


def test_point_at_interpolates_and_clamps():
    points = [(0.0, 0.0), (1.0, 0.0)]
    cum = np.array([0.0, 10.0])
    assert point_at(points, cum, 5) == pytest.approx((0.5, 0.0))
    assert point_at(points, cum, -1) == (0.0, 0.0)
    assert point_at(points, cum, 99) == (1.0, 0.0)


def test_slice_between_has_interpolated_ends():
    points = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
    cum = np.array([0.0, 10.0, 20.0, 30.0])
    piece = slice_between(points, cum, 5, 25)
    assert piece[0] == pytest.approx((0.5, 0.0))
    assert piece[1:-1] == [(1.0, 0.0), (2.0, 0.0)]
    assert piece[-1] == pytest.approx((2.5, 0.0))


def test_simplify_drops_collinear_points_and_keeps_corners():
    line = [(0.0, float(i)) for i in range(10)]
    assert simplify_indices(line, 0.001) == [0, 9]
    zigzag = [(0.0, 0.0), (1.0, 1.0), (0.0, 2.0), (1.0, 3.0)]
    assert simplify_indices(zigzag, 0.01) == [0, 1, 2, 3]


@pytest.mark.parametrize(
    ("total", "interval", "expected"),
    [
        (100, 25, [0, 25, 50, 75, 100]),
        (100.5, 25, [0, 25, 50, 75, 100.5]),  # mile 100 is within 1 mi of the end: merged
        (101.5, 25, [0, 25, 50, 75, 100, 101.5]),
        (10, 25, [0, 10]),
        (0, 25, [0]),
    ],
)
def test_checkpoints_always_include_both_ends(total, interval, expected):
    assert checkpoint_miles(total, interval) == expected


def test_attribution_tiles_the_route():
    assert attribution_bounds([0, 25, 50, 60]) == [(0, 12.5), (12.5, 37.5), (37.5, 55), (55, 60)]


@pytest.mark.parametrize("total", [0.4, 7, 49.9, 333.3, 1003.4])
@pytest.mark.parametrize("interval", [10, 25, 50])
def test_attributed_miles_sum_to_route_length(total, interval):
    bounds = attribution_bounds(checkpoint_miles(total, interval))
    assert sum(b - a for a, b in bounds) == pytest.approx(total)


def test_place_checkpoints_on_a_known_route():
    track = straight_track(total_mi=100, speed_mph=50)
    slots = place_checkpoints(track, 25)
    assert [round(s.mile) for s in slots] == [0, 25, 50, 75, 100]
    assert (slots[0].lat, slots[0].lon) == track.points[0]
    assert (slots[-1].lat, slots[-1].lon) == pytest.approx(track.points[-1])
    assert [round(s.elapsed_s) for s in slots] == [0, 1800, 3600, 5400, 7200]


def test_time_profile_prefers_progress_data():
    cum = np.array([0.0, 10.0, 20.0, 30.0])
    elapsed, source = build_time_profile(cum, 9999, progress=[(0, 0), (2, 1000), (3, 1500)])
    assert source == "progress"
    assert elapsed.tolist() == [0, 500, 1000, 1500]


def test_time_profile_falls_back_to_instructions():
    cum = np.array([0.0, 10.0, 20.0])
    elapsed, source = build_time_profile(
        cum, 1800, progress=[(0, 0), (99, 5)], instruction_anchors=[(0, 0), (16_093.44, 600)]
    )
    assert source == "instructions"  # progress index 99 is out of range
    assert elapsed.tolist() == pytest.approx([0, 600, 1800])


def test_time_profile_proportional_fallback():
    elapsed, source = build_time_profile(np.array([0.0, 10.0, 20.0]), 2000)
    assert source == "proportional"
    assert elapsed.tolist() == [0, 1000, 2000]


def test_time_profile_never_runs_backwards():
    cum = np.array([0.0, 10.0, 20.0])
    elapsed, _ = build_time_profile(cum, 100, progress=[(0, 0), (1, 80), (2, 60)])
    assert elapsed.tolist() == [0, 80, 80]
