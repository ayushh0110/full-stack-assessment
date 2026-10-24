"""Daily request budgets that keep us inside the providers' free tiers.

Each outbound call increments a per-provider counter in the shared cache (Redis in production).
Once a budget is spent, new work for that provider fails fast with 503 while cached results keep
working.
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.conf import settings
from django.core.cache import cache

from trips.exceptions import QuotaExhausted

LABELS = {
    "tomtom_routing": "routing",
    "osrm": "routing",
    "photon": "place search",
}
TTL_S = 2 * 24 * 3600


def _key(provider: str) -> str:
    return f"quota:{provider}:{datetime.now(UTC):%Y-%m-%d}"


def consume(provider: str, amount: int = 1) -> None:
    limit = settings.QUOTAS.get(provider)
    if not limit or amount <= 0:
        return
    key = _key(provider)
    cache.add(key, 0, timeout=TTL_S)
    try:
        used = cache.incr(key, amount)
    except ValueError:  # evicted between add and incr
        cache.set(key, amount, timeout=TTL_S)
        used = amount
    if used > limit:
        raise QuotaExhausted(
            f"Today's {LABELS.get(provider, provider)} quota is used up. Results already "
            "cached still work; new requests resume tomorrow (UTC)."
        )


def usage() -> dict[str, dict[str, int]]:
    return {
        provider: {"used": cache.get(_key(provider), 0), "limit": limit}
        for provider, limit in settings.QUOTAS.items()
    }
