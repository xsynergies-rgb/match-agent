"""One error shape for every API response.

Every refusal reaches the client as ``{"message", "code", "errors"}``: ``message`` is the first
sentence written for a person, ``code`` the first machine code (what the app branches on), and
``errors`` the full detail, field by field. Throttled responses also say when to retry.
"""

import math

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework import status
from rest_framework.exceptions import APIException, Throttled
from rest_framework.views import exception_handler


class Conflict(APIException):
    """The request is valid but the current state forbids it (a full match, a handled booking)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = gettext_lazy("This can't be done right now.")
    default_code = "conflict"


class InvalidCredentials(APIException):
    """A refused sign-in. 401, unlike DRF's AuthenticationFailed, which becomes 403 on public views."""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = gettext_lazy("Phone number or password is incorrect.")
    default_code = "invalid_credentials"


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = gettext_lazy("The service is temporarily unavailable. Try again shortly.")
    default_code = "unavailable"


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value)


def _first(value):
    """The first non-empty leaf, looking at ``detail`` before anything else."""
    if isinstance(value, dict):
        if "detail" in value:
            return _first(value["detail"])
        for item in value.values():
            found = _first(item)
            if found:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _first(item)
            if found:
                return found
        return None
    return str(value) if value else None


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    errors = _plain(response.data)
    codes = exc.get_codes() if isinstance(exc, APIException) else None
    body = {
        "message": _first(errors) or _("Request failed."),
        "code": _first(codes) or "error",
        "errors": errors,
    }
    if isinstance(exc, Throttled) and exc.wait is not None:
        body["retry_after"] = math.ceil(exc.wait)
    response.data = body
    return response
