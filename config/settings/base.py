"""Settings shared by every environment.

Defaults here are the safe ones: DEBUG off, no hosts allowed, every endpoint behind a signed-in
user. ``local.py`` loosens them for development and ``production.py`` adds what only production
needs, refusing to start when something required is missing.
"""

import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

from .database import database_from_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY must be set.")

DEBUG = False
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "apps.users",
    "apps.booking",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "common.middleware.ClientAddressMiddleware",
    "common.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Postgres when DATABASE_URL is set (production requires it), SQLite for quick local runs.
if os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": database_from_url(
            os.environ["DATABASE_URL"], sslmode=os.environ.get("DB_SSLMODE", "require")
        )
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"

# Players and staff sign in with their phone number and a password.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English")), ("fr", _("French")), ("ar", _("Arabic"))]
TIME_ZONE = "Africa/Casablanca"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/minute",
        "user": "300/minute",
        # Password guessing is limited per address and, whatever the address, per phone number.
        "auth_register": "10/hour",
        "auth_login": "20/minute",
        "auth_login_phone": "20/hour",
        "password_change": "10/hour",
        # Sign-in codes (off for now) cost money to send and are guessable if tried often enough.
        "otp_request": "10/hour",
        "otp_request_phone": "5/hour",
        "otp_verify": "30/hour",
        "otp_verify_phone": "10/hour",
        "auth_refresh": "60/minute",
        "reservation_create": "30/hour",
    },
    # ClientAddressMiddleware has already put the real client address in REMOTE_ADDR.
    "NUM_PROXIES": 0,
    "TIME_FORMAT": "%H:%M",
    "TIME_INPUT_FORMATS": ["%H:%M", "iso-8601"],
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    # A session lasts 30 days of inactivity on the phone; each refresh hands out a new refresh
    # token and retires the old one. A password change revokes access tokens at once (the token
    # carries a hash of the password) and the User model retires every refresh token.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "CHECK_REVOKE_TOKEN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# The generated docs (/api/docs/, DEBUG only) can't infer every hand-written APIView's body;
# API.md is the contract. Don't let that bury real warnings in `manage.py check`.
SILENCED_SYSTEM_CHECKS = ["drf_spectacular.W001", "drf_spectacular.W002"]

SPECTACULAR_SETTINGS = {
    "TITLE": "Glocal Sport API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# Phone numbers: accounts are keyed by the E.164 form of a mobile number from these countries.
PHONE_DEFAULT_REGION = "MA"
# Only these countries can receive a code. Keeping it tight stops bots from making the service
# text expensive foreign numbers ("SMS pumping").
PHONE_ALLOWED_REGIONS = env_list("PHONE_ALLOWED_REGIONS", "MA")
# Sign-in by one-time code (WhatsApp/SMS). Off for now: players use a password. Turning it on
# needs Twilio in production (see production.py and the README).
PHONE_CODES_ENABLED = os.environ.get("PHONE_CODES_ENABLED", "").lower() in ("1", "true", "yes")
OTP_SENDER = os.environ.get("OTP_SENDER", "console")  # console | twilio | memory (tests)
# How codes can be delivered, preferred first: "sms", "whatsapp", or both ("whatsapp,sms").
# The app offers the others as "Send by … instead" (e.g. for a number without WhatsApp).
OTP_CHANNELS = env_list("OTP_CHANNELS", "sms")
OTP_CODE_TTL = timedelta(minutes=10)
OTP_RESEND_COOLDOWN = timedelta(seconds=30)
OTP_MAX_ATTEMPTS = 5
OTP_DEBUG_RESPONSE = False  # local.py turns it on so the app can be tested without a phone

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM", "")  # an SMS number, or a Messaging Service SID (MG…)
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")
TWILIO_WHATSAPP_CONTENT_SID = os.environ.get("TWILIO_WHATSAPP_CONTENT_SID", "")

# Booking rules.
BOOKING_MAX_PENDING_PER_PLAYER = 5
BOOKING_WINDOW_DAYS = 14

# Phones promoted to staff at every start by `manage.py sync_admins` (accounts are never created).
GLOCAL_ADMIN_PHONES = env_list("GLOCAL_ADMIN_PHONES")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_context": {"()": "common.logging.RequestContextFilter"}},
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"},
        "json": {"()": "common.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "filters": ["request_context"], "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.server": {"level": "WARNING"}},
}
