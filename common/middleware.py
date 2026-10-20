import logging
import re
import time
import uuid

from .logging import request_id_var

access_logger = logging.getLogger("glocal.access")
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class ClientAddressMiddleware:
    """Put the caller's real address in REMOTE_ADDR, which the per-address throttles count by.

    Behind Render's proxy every request comes from the proxy. The last entry of
    ``X-Forwarded-For`` is the one Render's proxy appended, so a caller cannot forge it; the
    earlier entries can be anything the caller sent and are ignored.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            address = forwarded.rsplit(",", 1)[-1].strip()
            if address:
                request.META["REMOTE_ADDR"] = address
        return self.get_response(request)


class RequestIDMiddleware:
    """Give every request an id, echo it in ``X-Request-ID``, and log one line per request.

    A well-formed incoming ``X-Request-ID`` is kept, so the app and the server can quote the
    same id; anything else is replaced.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.monotonic()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            access_logger.info(
                "%s %s %s %dms",
                request.method,
                request.path,
                response.status_code,
                (time.monotonic() - started) * 1000,
            )
            return response
        finally:
            request_id_var.reset(token)
