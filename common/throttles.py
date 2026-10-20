import hashlib

from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class AddressThrottle(SimpleRateThrottle):
    """Counts requests per client address, signed in or not."""

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class IdentifierThrottle(SimpleRateThrottle):
    """Counts requests per value of a body field (hashed), whoever sends them.

    An address limit alone lets one attacker spread guesses for a single phone number over many
    addresses; this caps what can happen to that number in total.
    """

    identifier_field = None

    def normalize(self, value):
        return value.strip().casefold()

    def get_cache_key(self, request, view):
        raw = request.data.get(self.identifier_field) if hasattr(request.data, "get") else None
        if not isinstance(raw, str) or not raw.strip():
            return None
        digest = hashlib.sha256(self.normalize(raw).encode("utf-8")).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class ScopedUserThrottle(UserRateThrottle):
    """A per-user limit with its own scope (and counter); set ``scope`` on the subclass."""
