"""Route sets live in the shared cache (Redis in production), keyed by a hash of their inputs.

Planning the same trip twice reuses the stored routes, and the assessment and heatmap endpoints
read them back without calling the routing provider again.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from django.conf import settings
from django.core.cache import cache

from trips.exceptions import RouteSetExpired

ID_PATTERN = re.compile(r"^rs_[0-9a-f]{20}$")


def route_set_id(inputs: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    return f"rs_{digest[:20]}"


def _key(rs_id: str) -> str:
    return f"rs:{rs_id}"


def find(rs_id: str) -> dict[str, Any] | None:
    if not ID_PATTERN.match(rs_id):
        return None
    return cache.get(_key(rs_id))


def load(rs_id: str) -> dict[str, Any]:
    route_set = find(rs_id)
    if route_set is None:
        raise RouteSetExpired()
    return route_set


def save(route_set: dict[str, Any]) -> None:
    cache.set(_key(route_set["id"]), route_set, timeout=settings.ROUTE_SET_TTL_S)
