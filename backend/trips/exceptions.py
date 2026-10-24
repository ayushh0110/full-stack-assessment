"""Application errors and the API's error format: {"error": {"code", "message", "fields"?}}."""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

log = logging.getLogger(__name__)


class TripError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid"

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class InvalidTrip(TripError):
    pass


class RouteSetExpired(TripError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "route_set_expired"

    def __init__(self) -> None:
        super().__init__("These routes have expired. Plan the trip again.")


class UpstreamError(TripError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "upstream_error"


class QuotaExhausted(TripError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "quota_exhausted"


def _body(code: str, message: str, fields: dict | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return {"error": error}


def api_exception_handler(exc: Exception, context: dict) -> Response | None:
    if isinstance(exc, TripError):
        fields = {exc.field: [exc.message]} if exc.field else None
        return Response(_body(exc.code, exc.message, fields), status=exc.status_code)

    response = exception_handler(exc, context)
    if response is None:
        log.exception("Unhandled error", exc_info=exc)
        return Response(
            _body("server_error", "Something went wrong on our side. Please try again."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if isinstance(exc, ValidationError):
        response.data = _body("invalid", "Please check the highlighted fields.", response.data)
    elif isinstance(exc, Throttled):
        wait = f" Try again in {exc.wait:.0f} s." if exc.wait else ""
        response.data = _body("throttled", f"Too many requests.{wait}")
    else:
        response.data = _body(
            getattr(exc, "default_code", "error"), str(getattr(exc, "detail", exc))
        )
    return response
