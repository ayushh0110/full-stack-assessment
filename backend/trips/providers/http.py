"""Shared HTTP client with timeouts and retries."""

from __future__ import annotations

import functools
import time

import httpx
from django.conf import settings

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@functools.cache
def client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(10.0, connect=5.0),
        headers={"User-Agent": settings.HTTP_USER_AGENT},
    )


def request(
    method: str,
    url: str,
    *,
    retries: int = 2,
    backoff_s: float = 0.5,
    http: httpx.Client | None = None,
    **kwargs,
) -> httpx.Response:
    """Send a request, retrying transport errors and 429/5xx responses with backoff."""
    http = http or client()
    for attempt in range(retries + 1):
        try:
            response = http.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt == retries:
                raise
        else:
            if response.status_code not in RETRYABLE_STATUS or attempt == retries:
                return response
        time.sleep(backoff_s * 2**attempt)
    raise AssertionError("unreachable")
