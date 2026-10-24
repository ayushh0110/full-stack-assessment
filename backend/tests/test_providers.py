import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from trips.domain.alternatives import Rect
from trips.domain.timeutil import HOUR
from trips.exceptions import QuotaExhausted, UpstreamError
from trips.providers import budget, osrm, photon, tomtom
from trips.providers.openmeteo import OpenMeteoClient, parse_series, snap

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
START = 1_792_886_400
UNITS = {
    "time": "unixtime",
    "wind_speed_10m": "mp/h",
    "rain": "inch",
    "showers": "inch",
    "snowfall": "inch",
}


def location(wind, rain, showers, snow, units=UNITS):
    return {
        "hourly_units": units,
        "hourly": {
            "time": [START + k * HOUR for k in range(len(wind))],
            "wind_speed_10m": wind,
            "rain": rain,
            "showers": showers,
            "snowfall": snow,
        },
    }


# --- Open-Meteo ------------------------------------------------------------------


def test_series_combines_rain_and_showers():
    series = parse_series(location([5, 6], [0.1, None], [0.05, 0.0], [0.0, 0.2]))
    assert series.start == START
    assert series.rain_in == pytest.approx((0.15, None))
    assert series.snow_in == (0.0, 0.2)


def test_snowfall_in_cm_is_converted():
    units = {**UNITS, "snowfall": "cm"}
    series = parse_series(location([5], [0], [0], [2.54], units))
    assert series.snow_in == pytest.approx((1.0,))


def test_unexpected_units_are_an_error():
    with pytest.raises(UpstreamError):
        parse_series(location([5], [0], [0], [0], {**UNITS, "wind_speed_10m": "km/h"}))


@respx.mock
def test_fetch_batches_and_caches():
    route = respx.get(OPEN_METEO).mock(
        return_value=httpx.Response(
            200,
            json=[
                location([5, 6], [0, 0], [0, 0], [0, 0]),
                location([9, 9], [0, 0], [0, 0], [0, 0]),
            ],
        )
    )
    client = OpenMeteoClient()
    a, b = (40.0, -100.0), (41.0, -100.0)
    first = client.fetch([a, b, a], START, START + HOUR)
    assert first[a].wind_mph == (5, 6) and first[b].wind_mph == (9, 9)
    assert route.call_count == 1
    params = route.calls[0].request.url.params
    assert params["latitude"] == "40.0000,41.0000"
    assert params["models"] == "gfs_seamless"
    assert params["precipitation_unit"] == "inch"

    again = client.fetch([b, a], START, START + HOUR)
    assert again == first and route.call_count == 1  # served from the cache
    assert budget.usage()["open_meteo"]["used"] == 2


@respx.mock
def test_failed_batch_becomes_unknown_not_low():
    respx.get(OPEN_METEO).mock(return_value=httpx.Response(500))
    result = OpenMeteoClient().fetch([(40.0, -100.0)], START, START + HOUR)
    assert result == {(40.0, -100.0): None}


def test_snap_to_lattice():
    assert snap(40.026, -99.974) == (40.05, -99.95)


# --- TomTom ------------------------------------------------------------------------


TOMTOM_ROUTE = {
    "summary": {"lengthInMeters": 3000, "travelTimeInSeconds": 300},
    "legs": [
        {
            "points": [
                {"latitude": 40.0, "longitude": -100.0},
                {"latitude": 40.01, "longitude": -100.0},
                {"latitude": 40.02, "longitude": -100.0},
            ]
        }
    ],
    "progress": [
        {"pointIndex": 0, "distanceInMeters": 0, "travelTimeInSeconds": 0},
        {"pointIndex": 2, "distanceInMeters": 3000, "travelTimeInSeconds": 300},
    ],
    "guidance": {
        "instructions": [
            {"routeOffsetInMeters": 0, "travelTimeInSeconds": 0, "roadNumbers": ["US-6"]},
            {"routeOffsetInMeters": 500, "travelTimeInSeconds": 60, "roadNumbers": ["I-80"]},
            {"routeOffsetInMeters": 3000, "travelTimeInSeconds": 300},
        ]
    },
}


def test_tomtom_route_parsing():
    raw = tomtom.parse_route(TOMTOM_ROUTE)
    assert raw.points[0] == (40.0, -100.0) and len(raw.points) == 3
    assert raw.progress == [(0, 0.0), (2, 300.0)]
    assert raw.instruction_anchors[1] == (500.0, 60.0)
    assert raw.via == "I-80"  # 2,500 m on I-80 vs 500 m on US-6


@respx.mock
def test_tomtom_request_uses_truck_mode():
    route = respx.get(url__startswith=tomtom.BASE_URL).mock(
        return_value=httpx.Response(200, json={"routes": [TOMTOM_ROUTE]})
    )
    later = datetime.now(UTC) + timedelta(hours=3)
    routes = tomtom.TomTomRouting(api_key="k").routes((40, -100), (41, -90), later, 73_000)
    assert len(routes) == 1
    params = route.calls[0].request.url.params
    assert params["travelMode"] == "truck"
    assert params["vehicleWeight"] == "33112"  # 73,000 lb in kg
    assert params.get_list("extendedRouteRepresentation") == ["distance", "travelTime"]
    assert params["departAt"].startswith(later.strftime("%Y-%m-%dT%H:%M"))


@respx.mock
def test_tomtom_avoid_areas_are_posted():
    route = respx.post(url__startswith=tomtom.BASE_URL).mock(
        return_value=httpx.Response(200, json={"routes": []})
    )
    tomtom.TomTomRouting(api_key="k").routes(
        (40, -100),
        (41, -90),
        datetime.now(UTC),
        50_000,
        max_alternatives=0,
        avoid=[Rect(40.1, -99.0, 40.5, -98.5)],
    )
    body = json.loads(route.calls[0].request.content)
    corner = body["avoidAreas"]["rectangles"][0]["southWestCorner"]
    assert corner == {"latitude": 40.1, "longitude": -99.0}


@respx.mock
def test_tomtom_no_route_is_explained_plainly():
    body = {
        "detailedError": {
            "code": "NO_ROUTE_FOUND",
            "message": "Engine error while executing route request: NO_ROUTE_FOUND: "
            "Origin and destination have different ProductId's.",
        }
    }
    respx.get(url__startswith=tomtom.BASE_URL).mock(return_value=httpx.Response(400, json=body))
    with pytest.raises(UpstreamError, match="no drivable route"):
        tomtom.TomTomRouting(api_key="k").routes((31, -99), (-41, 174), datetime.now(UTC), 50_000)


@respx.mock
def test_tomtom_bad_key():
    respx.get(url__startswith=tomtom.BASE_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(UpstreamError, match="API key"):
        tomtom.TomTomRouting(api_key="bad").routes((40, -100), (41, -90), datetime.now(UTC), 50_000)


# --- OSRM and Photon ----------------------------------------------------------------


def test_osrm_progress_from_segment_durations():
    raw = osrm.parse_route(
        {
            "distance": 2000.0,
            "duration": 120.0,
            "geometry": {"coordinates": [[-100.0, 40.0], [-100.0, 40.01], [-100.0, 40.02]]},
            "legs": [{"annotation": {"duration": [50.0, 70.0]}}],
        }
    )
    assert raw.points[0] == (40.0, -100.0)
    assert raw.progress == [(0, 0.0), (1, 50.0), (2, 120.0)]


def test_photon_labels_are_readable_and_unique():
    feature = {
        "geometry": {"coordinates": [-104.98, 39.74]},
        "properties": {"name": "Denver", "state": "Colorado", "country": "United States"},
    }
    places = photon.parse_features({"features": [feature, feature]})
    assert [p.label for p in places] == ["Denver, Colorado, United States"]
    assert (places[0].lat, places[0].lon) == (39.74, -104.98)


# --- budgets -------------------------------------------------------------------------


def test_budget_stops_at_the_limit(settings):
    settings.QUOTAS = {"photon": 2}
    budget.consume("photon")
    budget.consume("photon")
    with pytest.raises(QuotaExhausted):
        budget.consume("photon")
