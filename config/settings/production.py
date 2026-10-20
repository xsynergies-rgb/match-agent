"""Production on Render. Fails closed: a missing required setting stops the start."""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import LOGGING, env_list
from .database import database_from_url


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production.")
    return value


DEBUG = False

# Render names the service's public host itself; ALLOWED_HOSTS adds any custom domains.
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS") + env_list("RENDER_EXTERNAL_HOSTNAME")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS (or RENDER_EXTERNAL_HOSTNAME) must be set in production.")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS") or [f"https://{host}" for host in ALLOWED_HOSTS]

DATABASES = {
    "default": database_from_url(required("DATABASE_URL"), sslmode=os.environ.get("DB_SSLMODE", "require"))
}

# Throttle counters must be shared by every gunicorn worker, so they live in the database
# (`manage.py createcachetable` runs at every start).
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "django_cache"}}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^api/health/$", r"^api/ready/$"]
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# Preloading is a promise about a whole domain you own; an onrender.com subdomain can't make it.
SILENCED_SYSTEM_CHECKS = [*SILENCED_SYSTEM_CHECKS, "security.W021"]  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

# Codes, when turned on, are really sent and never returned in a response.
OTP_DEBUG_RESPONSE = False
if PHONE_CODES_ENABLED:  # noqa: F405
    if OTP_SENDER != "twilio":  # noqa: F405
        raise ImproperlyConfigured("OTP_SENDER must be 'twilio' in production.")
    required("TWILIO_ACCOUNT_SID")
    required("TWILIO_AUTH_TOKEN")
    if not OTP_CHANNELS or set(OTP_CHANNELS) - {"sms", "whatsapp"}:  # noqa: F405
        raise ImproperlyConfigured("OTP_CHANNELS must list 'sms' and/or 'whatsapp'.")
    if "whatsapp" in OTP_CHANNELS:  # noqa: F405
        required("TWILIO_WHATSAPP_FROM")
        required("TWILIO_WHATSAPP_CONTENT_SID")
    if "sms" in OTP_CHANNELS:  # noqa: F405
        required("TWILIO_FROM")

LOGGING = {
    **LOGGING,
    "handlers": {**LOGGING["handlers"], "console": {**LOGGING["handlers"]["console"], "formatter": "json"}},
}
