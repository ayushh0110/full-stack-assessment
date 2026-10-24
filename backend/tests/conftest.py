import pytest
from django.core.cache import cache

from trips.providers import http


@pytest.fixture(autouse=True)
def clean_state(settings, monkeypatch):
    settings.TOMTOM_API_KEY = ""
    cache.clear()
    monkeypatch.setattr(http.time, "sleep", lambda _s: None)  # no real backoff in tests
    yield
    cache.clear()
