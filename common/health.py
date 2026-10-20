"""Liveness and readiness for Render.

Liveness says the process answers. Readiness says it can serve a request, which for this API
means the database answers; Render's health check uses readiness.
"""

import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)
NO_STORE = {"Cache-Control": "no-store"}


def liveness(_request):
    return JsonResponse({"status": "ok"}, headers=NO_STORE)


def readiness(_request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        # The reason belongs in the logs, not in the body handed to whoever is probing.
        logger.exception("Readiness check failed: the database did not answer.")
        return JsonResponse({"status": "unavailable"}, status=503, headers=NO_STORE)
    return JsonResponse({"status": "ok"}, headers=NO_STORE)
