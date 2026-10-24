"""End-to-end API tests with fake routing and weather providers."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient

from trips import services
from trips.domain.geo import METERS_PER_MILE
from trips.domain.weather import HourlySeries
from trips.providers import budget
from trips.providers.types import RawRoute

from .helpers import straight_track

DENVER = ZoneInfo("America/Denver")


class FakeRouting:
    name = "fake"
    truck_aware = True
    supports_avoid_areas = False

    def __init__(self):
        self.calls = 0

    def routes(self, origin, destination, depart_at, gross_lb, *, max_alternatives=2, avoid=()):
        self.calls += 1
        raws = []
        # A is fastest but runs through high wind; B moderate wind; C calm but slowest.
        for offset_mi, speed in ((0, 50), (20, 45), (40, 40)):
            track = straight_track(200, n=201, speed_mph=speed, lon_offset_mi=offset_mi)
            raws.append(
                RawRoute(
                    points=track.points,
                    length_m=track.total_mi * METERS_PER_MILE,
                    duration_s=track.duration_s,
                    progress=list(enumerate(track.elapsed_s.tolist())),
                )
            )
        return raws


class FakeWeather:
    """Wind depends on longitude: ~50 mph around route A, 30 mph around B, 10 mph around C."""

    def __init__(self, missing_west_of=None):
        self.missing_west_of = missing_west_of

    def fetch(self, locations, start, end):
        hours = (end - start) // 3600 + 1
        result = {}
        for lat, lon in locations:
            if self.missing_west_of is not None and lon < self.missing_west_of:
                result[(lat, lon)] = None
                continue
            wind = 50.0 if lon <= -99.9 else 30.0 if lon <= -99.5 else 10.0
            result[(lat, lon)] = HourlySeries(
                start, (wind,) * hours, (0.0,) * hours, (0.0,) * hours
            )
        return result


@pytest.fixture
def fakes(monkeypatch):
    routing, weather = FakeRouting(), FakeWeather()
    monkeypatch.setattr(services, "routing_provider", lambda: routing)
    monkeypatch.setattr(services, "weather_client", lambda: weather)
    return routing, weather


@pytest.fixture
def api():
    return APIClient()


def departure(hours_ahead: float = 2) -> str:
    return (datetime.now(DENVER) + timedelta(hours=hours_ahead)).strftime("%Y-%m-%dT%H:%M")


def trip(**overrides):
    body = {
        "origin": {"lat": 35.0, "lon": -100.0, "label": "Origin"},
        "destination": {"lat": 37.9, "lon": -100.0, "label": "Destination"},
        "departure_local": departure(),
        "load_lb": 38_000,
    }
    return {**body, **overrides}


def create(api, **overrides):
    return api.post("/api/v1/route-sets", trip(**overrides), format="json")


def test_health(api):
    body = api.get("/api/v1/health").json()
    assert body["status"] == "ok" and body["cache"] == "ok"


def test_create_route_set(api, fakes):
    response = create(api)
    assert response.status_code == 201
    body = response.json()
    assert [r["id"] for r in body["routes"]] == ["A", "B", "C"]  # fastest first
    assert body["origin_tz"] == "America/Chicago"  # 35N, 100W is in the Texas panhandle
    assert body["routing_gross_lb"] == 38_000 + 35_000
    assert body["routes"][0]["distance_mi"] == pytest.approx(200, abs=0.5)
    assert len(body["routes"][0]["geometry"]) == len(body["routes"][0]["elapsed_s"])


def test_same_trip_reuses_routes(api, fakes):
    routing, _ = fakes
    first = create(api).json()
    second = create(api).json()
    assert first["id"] == second["id"]
    assert routing.calls == 1


def test_assessment_and_recommendation(api, fakes):
    rs = create(api).json()
    body = api.get(f"/api/v1/route-sets/{rs['id']}/assessment", {"interval_mi": 25}).json()
    routes = {r["id"]: r for r in body["routes"]}
    assert [round(cp["mile"]) for cp in routes["A"]["checkpoints"]] == [
        0,
        25,
        50,
        75,
        100,
        125,
        150,
        175,
        200,
    ]
    assert sum(routes["B"]["summary"]["miles_by_level"].values()) == pytest.approx(200, abs=0.2)
    assert routes["A"]["checkpoints"][0]["level"] == 4  # 50 mph with 38,000 lb > 30,000: No Travel
    assert "load rule" in routes["A"]["checkpoints"][0]["reasons"][0]
    rec = body["recommendation"]
    assert rec["status"] == "recommended"
    assert rec["route_id"] == "C"  # B and C tie on Severe/High; C has the lower risk index
    assert "lower risk index" in rec["explanation"]
    assert [(e["route_id"], e["reason"]) for e in rec["excluded"]] == [("A", "no_travel")]
    assert routes["C"]["segments"][0]["level"] == 0


def test_missing_weather_excludes_the_route(api, fakes, monkeypatch):
    monkeypatch.setattr(services, "weather_client", lambda: FakeWeather(missing_west_of=-99.9))
    rs = create(api).json()
    body = api.get(f"/api/v1/route-sets/{rs['id']}/assessment").json()
    route_a = next(r for r in body["routes"] if r["id"] == "A")
    assert route_a["summary"]["coverage"] == 0
    assert route_a["checkpoints"][0]["level"] is None
    assert ("A", "incomplete") in [
        (e["route_id"], e["reason"]) for e in body["recommendation"]["excluded"]
    ]


def test_heatmap(api, fakes):
    rs = create(api).json()
    body = api.get(f"/api/v1/route-sets/{rs['id']}/heatmap").json()
    assert body["hours"] == 49 and len(body["risk"]) == 49
    assert 0 < len(body["cells"]) <= 400
    assert all(len(frame) == len(body["cells"]) for frame in body["risk"])
    assert {4, 1, 0} <= set(body["risk"][0])


def test_interval_must_be_10_25_or_50(api, fakes):
    rs = create(api).json()
    response = api.get(f"/api/v1/route-sets/{rs['id']}/assessment", {"interval_mi": 15})
    assert response.status_code == 400
    assert "interval_mi" in response.json()["error"]["fields"]


def test_unknown_route_set(api):
    response = api.get("/api/v1/route-sets/rs_00000000000000000000/assessment")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "route_set_expired"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"load_lb": 90_000}, "load_lb"),
        ({"load_lb": -1}, "load_lb"),
        ({"departure_local": "2026-10-25T07:00:00-06:00"}, "departure_local"),
        ({"departure_local": "tomorrow"}, "departure_local"),
        ({"destination": {"lat": 35.0, "lon": -100.0}}, "destination"),
    ],
)
def test_validation_errors(api, fakes, overrides, field):
    response = create(api, **overrides)
    assert response.status_code == 400
    assert field in response.json()["error"]["fields"]


def test_departure_in_a_daylight_saving_gap(api, fakes):
    denver = {"lat": 39.74, "lon": -104.99, "label": "Denver"}
    response = create(api, origin=denver, departure_local="2026-03-08T02:30")
    assert response.status_code == 400
    assert "does not exist" in response.json()["error"]["message"]


def test_departure_must_be_within_forecast_range(api, fakes):
    response = create(api, departure_local=departure(hours_ahead=24 * 8))
    assert response.status_code == 400
    assert "7 days" in response.json()["error"]["message"]


def test_quota_exhaustion_returns_503(api, settings):
    settings.QUOTAS = {"photon": 1}
    budget.consume("photon")  # spend the only call
    response = api.get("/api/v1/geocode", {"q": "denver"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "quota_exhausted"
