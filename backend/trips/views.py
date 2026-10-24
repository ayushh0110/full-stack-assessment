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
    GeocodeQuerySerializer,
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


class AssessmentView(APIView):
    throttle_scope = "reads"

    def get(self, request: Request, rs_id: str) -> Response:
        query = AssessmentQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(services.assess(rs_id, query.validated_data["interval_mi"]))


class HeatmapView(APIView):
    throttle_scope = "reads"

    def get(self, request: Request, rs_id: str) -> Response:
        return Response(services.heatmap(rs_id))
