"""Test runs: in-memory SQLite, codes kept in memory, throttles out of the way."""

import os

os.environ.setdefault("SECRET_KEY", "test-only-not-a-secret")

from .base import *  # noqa: E402,F403
from .base import REST_FRAMEWORK

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

OTP_SENDER = "memory"
OTP_CHANNELS = ["whatsapp", "sms"]
OTP_DEBUG_RESPONSE = False

# Tests that exercise a throttle lower its rate themselves.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {scope: "10000/minute" for scope in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]},
}

LOGGING = {  # quiet test output; failures still print
    **LOGGING,  # noqa: F405
    "handlers": {"console": {**LOGGING["handlers"]["console"], "level": "CRITICAL"}},  # noqa: F405
}
