"""End-to-end API tests with a fake routing provider and browser-relayed forecasts."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient

from trips import services
from trips.domain.geo import METERS_PER_MILE
from trips.domain.timeutil import HOUR
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


def open_meteo_item(lat, lon, start, hours, wind):
    """A location object shaped like Open-Meteo's response, as the browser relays it."""
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly_units": {
            "time": "unixtime",
            "wind_speed_10m": "mp/h",
            "rain": "inch",
            "showers": "inch",
            "snowfall": "inch",
        },
        "hourly": {
            "time": [start + k * HOUR for k in range(hours)],
            "wind_speed_10m": [wind] * hours,
            "rain": [0.0] * hours,
            "showers": [0.0] * hours,
            "snowfall": [0.0] * hours,
        },
    }


def relay(request_body, missing_west_of=None):
    """Play the browser: fetch a forecast for every requested location. Wind depends on
    longitude: ~50 mph around route A, 30 mph around B, 10 mph around C."""
    forecast = request_body["forecast"]
    start = int(datetime.fromisoformat(forecast["params"]["start_hour"] + "+00:00").timestamp())
    end = int(datetime.fromisoformat(forecast["params"]["end_hour"] + "+00:00").timestamp())
    hours = (end - start) // HOUR + 1
    items = []
    for lat, lon in forecast["locations"]:
        if missing_west_of is not None and lon < missing_west_of:
            items.append(None)
            continue
        wind = 50.0 if lon <= -99.9 else 30.0 if lon <= -99.5 else 10.0
        items.append(open_meteo_item(lat, lon, start, hours, wind))
    return items


@pytest.fixture
def routing(monkeypatch):
    fake = FakeRouting()
    monkeypatch.setattr(services, "routing_provider", lambda: fake)
    return fake


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


def assess(api, rs_id, interval=25, missing_west_of=None):
    url = f"/api/v1/route-sets/{rs_id}/assessment"
    request = api.get(f"{url}/forecast-request", {"interval_mi": interval}).json()
    forecasts = relay(request, missing_west_of)
    return api.post(url, {"interval_mi": interval, "forecasts": forecasts}, format="json")


def test_health(api):
    body = api.get("/api/v1/health").json()
    assert body["status"] == "ok" and body["cache"] == "ok"


def test_create_route_set(api, routing):
    response = create(api)
    assert response.status_code == 201
    body = response.json()
    assert [r["id"] for r in body["routes"]] == ["A", "B", "C"]  # fastest first
    assert body["origin_tz"] == "America/Chicago"  # 35N, 100W is in the Texas panhandle
    assert body["routing_gross_lb"] == 38_000 + 35_000
    assert body["routes"][0]["distance_mi"] == pytest.approx(200, abs=0.5)
    assert len(body["routes"][0]["geometry"]) == len(body["routes"][0]["elapsed_s"])


def test_same_trip_reuses_routes(api, routing):
    first = create(api).json()
    second = create(api).json()
    assert first["id"] == second["id"]
    assert routing.calls == 1


class TwoRouteRouting(FakeRouting):
    """Returns two routes, plus a third corridor only when asked to avoid both of them."""

    supports_avoid_areas = True

    def __init__(self):
        super().__init__()
        self.avoided = []

    def routes(self, origin, destination, depart_at, gross_lb, *, max_alternatives=2, avoid=()):
        raws = super().routes(origin, destination, depart_at, gross_lb)
        if not avoid:
            return raws[:2]
        self.avoided = list(avoid)
        covers = {
            raw_lon
            for raw_lon in (-100.0, -99.6466)
            if any(r.west <= raw_lon <= r.east for r in avoid)
        }
        return [raws[2]] if len(covers) == 2 else [raws[1]]


def test_fallback_avoids_every_existing_route(api, monkeypatch):
    fake = TwoRouteRouting()
    monkeypatch.setattr(services, "routing_provider", lambda: fake)
    body = create(api).json()
    assert [r["id"] for r in body["routes"]] == ["A", "B", "C"]
    assert 0 < len(fake.avoided) <= 10  # TomTom's limit
    assert body["notes"] == []


class TooSlowThirdRouting(TwoRouteRouting):
    """Two routes; the only way around both takes twice as long."""

    def routes(self, origin, destination, depart_at, gross_lb, *, max_alternatives=2, avoid=()):
        raws = FakeRouting.routes(self, origin, destination, depart_at, gross_lb)
        if not avoid:
            return raws[:2]
        third = straight_track(200, n=201, speed_mph=25, lon_offset_mi=40)
        return [
            RawRoute(
                points=third.points,
                length_m=third.total_mi * METERS_PER_MILE,
                duration_s=third.duration_s,
                progress=list(enumerate(third.elapsed_s.tolist())),
            )
        ]


def test_missing_third_route_is_explained(api, monkeypatch):
    monkeypatch.setattr(services, "routing_provider", lambda: TooSlowThirdRouting())
    body = create(api).json()
    assert [r["id"] for r in body["routes"]] == ["A", "B"]
    assert body["notes"] == [
        "The routing service found 2 distinct routes for this trip. A third isn't shown "
        "because the best other route is 100% longer than the fastest."
    ]


class SlowThirdRouting(FakeRouting):
    def routes(self, origin, destination, depart_at, gross_lb, *, max_alternatives=2, avoid=()):
        raws = []
        for offset_mi, speed in ((0, 50), (20, 45), (40, 34)):  # C takes ~47% longer than A
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


def test_long_detours_are_labelled(api, monkeypatch):
    monkeypatch.setattr(services, "routing_provider", lambda: SlowThirdRouting())
    routes = {r["id"]: r for r in create(api).json()["routes"]}
    assert (routes["A"]["long_detour"], routes["A"]["detour_pct"]) == (False, 0)
    assert (routes["B"]["long_detour"], routes["B"]["detour_pct"]) == (False, 11)
    assert routes["C"]["long_detour"] is True
    assert routes["C"]["detour_pct"] == 47


def test_forecast_request_lists_unique_checkpoint_locations(api, routing):
    rs = create(api).json()
    body = api.get(
        f"/api/v1/route-sets/{rs['id']}/assessment/forecast-request", {"interval_mi": 25}
    ).json()
    forecast = body["forecast"]
    assert forecast["url"].startswith("https://api.open-meteo.com/")
    assert forecast["params"]["models"] == "gfs_seamless"
    locations = [tuple(loc) for loc in forecast["locations"]]
    assert len(locations) == len(set(locations)) <= 3 * 9


def test_assessment_and_recommendation(api, routing):
    rs = create(api).json()
    body = assess(api, rs["id"]).json()
    routes = {r["id"]: r for r in body["routes"]}
    miles = [round(cp["mile"]) for cp in routes["A"]["checkpoints"]]
    assert miles == [0, 25, 50, 75, 100, 125, 150, 175, 200]
    assert sum(routes["B"]["summary"]["miles_by_level"].values()) == pytest.approx(200, abs=0.2)
    assert routes["A"]["checkpoints"][0]["level"] == 4  # 50 mph with 38,000 lb > 30,000: No Travel
    assert "load rule" in routes["A"]["checkpoints"][0]["reasons"][0]
    rec = body["recommendation"]
    assert rec["status"] == "recommended"
    assert rec["route_id"] == "C"  # B and C tie on Severe/High; C has the lower risk index
    assert "lower risk index" in rec["explanation"]
    assert [(e["route_id"], e["reason"]) for e in rec["excluded"]] == [("A", "no_travel")]
    assert routes["C"]["segments"][0]["level"] == 0


def test_missing_weather_excludes_the_route(api, routing):
    rs = create(api).json()
    body = assess(api, rs["id"], missing_west_of=-99.9).json()
    route_a = next(r for r in body["routes"] if r["id"] == "A")
    assert route_a["summary"]["coverage"] == 0
    assert route_a["checkpoints"][0]["level"] is None
    excluded = [(e["route_id"], e["reason"]) for e in body["recommendation"]["excluded"]]
    assert ("A", "incomplete") in excluded


def test_wrong_number_of_forecasts_is_rejected(api, routing):
    rs = create(api).json()
    response = api.post(
        f"/api/v1/route-sets/{rs['id']}/assessment",
        {"interval_mi": 25, "forecasts": [None]},
        format="json",
    )
    assert response.status_code == 400
    assert "forecasts" in response.json()["error"]["fields"]


def test_heatmap(api, routing):
    rs = create(api).json()
    url = f"/api/v1/route-sets/{rs['id']}/heatmap"
    request = api.get(f"{url}/forecast-request").json()
    body = api.post(
        url, {"start_utc": request["start_utc"], "forecasts": relay(request)}, format="json"
    ).json()
    assert body["hours"] == 49 and len(body["risk"]) == 49
    assert 0 < len(body["cells"]) <= 400
    assert all(len(frame) == len(body["cells"]) for frame in body["risk"])
    assert {4, 1, 0} <= set(body["risk"][0])


def test_heatmap_start_must_be_recent(api, routing):
    rs = create(api).json()
    stale = (datetime.now(UTC) - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    response = api.post(
        f"/api/v1/route-sets/{rs['id']}/heatmap",
        {"start_utc": stale.isoformat(), "forecasts": []},
        format="json",
    )
    assert response.status_code == 400
    assert "start_utc" in response.json()["error"]["fields"]


def test_interval_must_be_10_25_or_50(api, routing):
    rs = create(api).json()
    response = api.get(
        f"/api/v1/route-sets/{rs['id']}/assessment/forecast-request", {"interval_mi": 15}
    )
    assert response.status_code == 400
    assert "interval_mi" in response.json()["error"]["fields"]


def test_unknown_route_set(api):
    response = api.get("/api/v1/route-sets/rs_00000000000000000000/assessment/forecast-request")
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
def test_validation_errors(api, routing, overrides, field):
    response = create(api, **overrides)
    assert response.status_code == 400
    assert field in response.json()["error"]["fields"]


def test_departure_in_a_daylight_saving_gap(api, routing):
    denver = {"lat": 39.74, "lon": -104.99, "label": "Denver"}
    response = create(api, origin=denver, departure_local="2026-03-08T02:30")
    assert response.status_code == 400
    assert "does not exist" in response.json()["error"]["message"]


def test_departure_must_be_within_forecast_range(api, routing):
    response = create(api, departure_local=departure(hours_ahead=24 * 8))
    assert response.status_code == 400
    assert "7 days" in response.json()["error"]["message"]


def test_quota_exhaustion_returns_503(api, settings):
    settings.QUOTAS = {"photon": 1}
    budget.consume("photon")  # spend the only call
    response = api.get("/api/v1/geocode", {"q": "denver"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "quota_exhausted"
