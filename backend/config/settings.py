import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
# Render provides the service's public hostname at runtime.
if render_host := os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(render_host)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "rest_framework",
    "trips",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Stateless API: no database, sessions or auth.
DATABASES: dict = {}

TEMPLATES: list = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = None
# The built SPA (frontend/dist) is copied here in the Docker image and served from "/", so the
# app and its API share one origin (no CORS). Vite's hashed /assets/ files are cached forever.
FRONTEND_DIST = BASE_DIR / "frontend_dist"
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.is_dir() else None
WHITENOISE_INDEX_FILE = True


def _immutable_asset(path: str, url: str) -> bool:
    return url.startswith("/assets/")


WHITENOISE_IMMUTABLE_FILE_TEST = _immutable_asset

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REDIS_URL = os.environ.get("REDIS_URL", "")
CACHES: dict[str, dict[str, Any]]
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "OPTIONS": {"MAX_ENTRIES": 100_000},
        }
    }

REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "geocode": os.environ.get("RATE_GEOCODE", "90/min"),
        "route_sets": os.environ.get("RATE_ROUTE_SETS", "20/min"),
        "reads": os.environ.get("RATE_READS", "60/min"),
    },
    # Behind Cloud Run / Render there is one proxy hop; the throttle must key on the real client IP.
    "NUM_PROXIES": env_int("NUM_PROXIES", 0),
    "EXCEPTION_HANDLER": "trips.exceptions.api_exception_handler",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    # httpx logs every request URL at INFO, and TomTom's URL carries the API key.
    "loggers": {
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
    },
}

# --- Providers -------------------------------------------------------------
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")
OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
# Pinned so the time meaning of each variable stays fixed (see weather.py).
OPEN_METEO_MODEL = os.environ.get("OPEN_METEO_MODEL", "gfs_seamless")
PHOTON_URL = os.environ.get("PHOTON_URL", "https://photon.komoot.io/api/")
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org/route/v1/driving")
HTTP_USER_AGENT = os.environ.get("HTTP_USER_AGENT", "weather-aware-truck-routing/1.0")

# --- Trip planning ---------------------------------------------------------
# Routing needs gross vehicle weight; the risk rules use the load as entered.
ROUTING_TARE_LB = env_int("ROUTING_TARE_LB", 35_000)
HEATMAP_MAX_CELLS = env_int("HEATMAP_MAX_CELLS", 400)
HEATMAP_BUFFER_MI = float(os.environ.get("HEATMAP_BUFFER_MI", 30))
ROUTE_SET_TTL_S = env_int("ROUTE_SET_TTL_S", 3600)
# Browsers relay Open-Meteo forecasts in the request body (a few hundred KB for long trips).
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Daily budgets that stop us running through the providers' free tiers. Weather isn't listed:
# each visitor's browser fetches it with that visitor's own Open-Meteo quota.
QUOTAS = {
    "tomtom_routing": env_int("QUOTA_TOMTOM_ROUTING_DAILY", 600),
    "osrm": env_int("QUOTA_OSRM_DAILY", 1_000),
    "photon": env_int("QUOTA_PHOTON_DAILY", 5_000),
}
