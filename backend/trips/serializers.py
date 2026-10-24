from __future__ import annotations

from datetime import datetime

from rest_framework import serializers

from trips.domain.geo import haversine_mi
from trips.providers.types import Place
from trips.services import TripRequest


class PlaceSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class RouteSetRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure_local = serializers.CharField(
        help_text="Wall-clock time at the origin, e.g. 2026-10-25T07:00 (no UTC offset)."
    )
    load_lb = serializers.IntegerField(min_value=0, max_value=80_000)

    def validate_departure_local(self, value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise serializers.ValidationError("Use the format YYYY-MM-DDTHH:MM.") from exc
        if parsed.tzinfo is not None:
            raise serializers.ValidationError(
                "Send the local time at the origin without a UTC offset."
            )
        return parsed.replace(second=0, microsecond=0)

    def validate(self, attrs: dict) -> dict:
        o, d = attrs["origin"], attrs["destination"]
        if haversine_mi((o["lat"], o["lon"]), (d["lat"], d["lon"])) < 0.5:
            raise serializers.ValidationError(
                {"destination": ["Choose a destination away from the origin."]}
            )
        return attrs

    def to_trip_request(self) -> TripRequest:
        data = self.validated_data
        return TripRequest(
            origin=Place(**data["origin"]),
            destination=Place(**data["destination"]),
            departure_local=data["departure_local"],
            load_lb=data["load_lb"],
        )


class AssessmentQuerySerializer(serializers.Serializer):
    interval_mi = serializers.ChoiceField(choices=[10, 25, 50], default=25)


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=3, max_length=200, trim_whitespace=True)
