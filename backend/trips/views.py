from __future__ import annotations

from django.core.cache import cache
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from trips import services
from trips.providers import budget
from trips.providers.photon import PhotonGeocoder
from trips.serializers import (
    AssessmentQuerySerializer,
    AssessmentRequestSerializer,
    GeocodeQuerySerializer,
    HeatmapRequestSerializer,
    RouteSetRequestSerializer,
)


class HealthView(APIView):
    throttle_classes = ()

    def get(self, request: Request) -> Response:
        cache.set("health:ping", "ok", timeout=10)
        return Response(
            {
                "status": "ok",
                "cache": "ok" if cache.get("health:ping") == "ok" else "unavailable",
                "routing_provider": services.routing_provider().name,
                "quotas": budget.usage(),
            }
        )


class GeocodeView(APIView):
    throttle_scope = "geocode"

    def get(self, request: Request) -> Response:
        query = GeocodeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        places = PhotonGeocoder().search(query.validated_data["q"])
        return Response(
            [
                {
                    "label": p.label,
                    "lat": p.lat,
                    "lon": p.lon,
                    "tz": services.timezone_at(p.lat, p.lon),
                }
                for p in places
            ]
        )


class RouteSetCreateView(APIView):
    throttle_scope = "route_sets"

    def post(self, request: Request) -> Response:
        body = RouteSetRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        route_set = services.create_route_set(body.to_trip_request())
        return Response(services.route_set_response(route_set), status=status.HTTP_201_CREATED)


class AssessmentForecastRequestView(APIView):
    """Step 1: which forecasts the browser should fetch for this route set and interval."""

    throttle_scope = "reads"

    def get(self, request: Request, rs_id: str) -> Response:
        query = AssessmentQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        interval = query.validated_data["interval_mi"]
        return Response(services.assessment_forecast_request(rs_id, interval))


class AssessmentView(APIView):
    """Step 2: score the routes from the forecasts the browser fetched."""

    throttle_scope = "reads"

    def post(self, request: Request, rs_id: str) -> Response:
        body = AssessmentRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        return Response(services.assess(rs_id, data["interval_mi"], data["forecasts"]))


class HeatmapForecastRequestView(APIView):
    throttle_scope = "reads"

    def get(self, request: Request, rs_id: str) -> Response:
        return Response(services.heatmap_forecast_request(rs_id))


class HeatmapView(APIView):
    throttle_scope = "reads"

    def post(self, request: Request, rs_id: str) -> Response:
        body = HeatmapRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        return Response(services.heatmap(rs_id, data["start_utc"], data["forecasts"]))
