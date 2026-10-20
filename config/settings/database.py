"""Build Django's database settings from a ``DATABASE_URL``.

Render hands the API one connection URL rather than five separate settings. It is parsed here,
without a dependency, so that a URL that is not a complete PostgreSQL URL is a configuration
error at startup, not a connection error at the first request.
"""

from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

POSTGRES_SCHEMES = ("postgres", "postgresql")


def database_from_url(url, *, conn_max_age=60, sslmode="require"):
    """Return a ``DATABASES["default"]`` entry for a PostgreSQL URL.

    Query parameters become connection options, so ``?sslmode=disable`` overrides the default.
    The port may be omitted, as Render's internal connection strings do.
    """
    parts = urlsplit(url or "")
    if parts.scheme not in POSTGRES_SCHEMES:
        raise ImproperlyConfigured("DATABASE_URL must be a postgres:// or postgresql:// URL.")
    name = unquote(parts.path.lstrip("/"))
    if not (parts.hostname and parts.username and name):
        raise ImproperlyConfigured("DATABASE_URL must name a host, a user, and a database.")
    try:
        port = parts.port or 5432
    except ValueError as error:
        raise ImproperlyConfigured("DATABASE_URL has an invalid port.") from error
    options = {key: values[-1] for key, values in parse_qs(parts.query).items()}
    options.setdefault("sslmode", sslmode)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parts.username),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname,
        "PORT": str(port),
        # Reuse connections between requests, and check a reused one before handing it out, so
        # a database restart costs one retry rather than errors.
        "CONN_MAX_AGE": conn_max_age,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": options,
    }
