"""Photon (OpenStreetMap) place search, built for type-ahead input. Results are cached for a day."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache

from trips.exceptions import UpstreamError

from . import budget
from .http import request
from .types import Place

CACHE_TTL_S = 24 * 3600


def _label(props: dict[str, Any]) -> str:
    street = " ".join(p for p in (props.get("housenumber"), props.get("street")) if p)
    head = props.get("name") or street
    parts = [head, props.get("city"), props.get("state"), props.get("country")]
    return ", ".join(dict.fromkeys(p for p in parts if p))


def parse_features(data: dict[str, Any]) -> list[Place]:
    places: dict[str, Place] = {}
    for feature in data.get("features", []):
        lon, lat = feature["geometry"]["coordinates"][:2]
        label = _label(feature.get("properties", {}))
        if label and label not in places:
            places[label] = Place(label=label, lat=float(lat), lon=float(lon))
    return list(places.values())


class PhotonGeocoder:
    def __init__(self, http: httpx.Client | None = None) -> None:
        self.http = http
        self.url = settings.PHOTON_URL

    def search(self, query: str, limit: int = 6) -> list[Place]:
        normalized = " ".join(query.lower().split())
        key = f"geo:{limit}:{normalized}"
        if (hit := cache.get(key)) is not None:
            return [Place(**p) for p in hit]
        budget.consume("photon")
        try:
            response = request(
                "GET",
                self.url,
                params={"q": normalized, "limit": limit, "lang": "en"},
                http=self.http,
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("Place search is unavailable right now.") from exc
        if response.status_code != 200:
            raise UpstreamError("Place search is unavailable right now.")
        places = parse_features(response.json())
        cache.set(key, [asdict(p) for p in places], timeout=CACHE_TTL_S)
        return places
