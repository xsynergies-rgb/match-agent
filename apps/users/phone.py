"""One canonical form for phone numbers: E.164 ("+212612345678").

People type numbers many ways ("06 12 34 56 78", "+212 612-345678", "00212612345678"). Every
number is parsed with libphonenumber and then stored, compared and rate-limited in E.164, so
one person is one account and one throttle bucket however they typed it.
"""

import phonenumbers
from django.conf import settings
from django.utils.translation import gettext_lazy as _

MOBILE_TYPES = (phonenumbers.PhoneNumberType.MOBILE, phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE)


class InvalidPhone(ValueError):
    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


def _parse(text):
    try:
        number = phonenumbers.parse(text, settings.PHONE_DEFAULT_REGION)
    except phonenumbers.NumberParseException:
        return None
    return number if phonenumbers.is_valid_number(number) else None


def normalize_phone(raw):
    """Return the E.164 form of a mobile number from an allowed country, or raise InvalidPhone."""
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidPhone(_("Enter your phone number."), code="required")
    text = raw.strip()
    if text.startswith("00"):
        text = "+" + text[2:]
    number = _parse(text)
    digits = "".join(ch for ch in text if ch.isdigit())
    if number is None and not text.startswith("+") and digits:
        # "212612345678": the country code typed without the plus.
        number = _parse("+" + digits)
    if number is None:
        raise InvalidPhone(_("Enter a valid phone number."))
    allowed = settings.PHONE_ALLOWED_REGIONS
    if allowed and phonenumbers.region_code_for_number(number) not in allowed:
        raise InvalidPhone(_("Sign-in isn't available for numbers from this country yet."), code="region_not_allowed")
    if phonenumbers.number_type(number) not in MOBILE_TYPES:
        raise InvalidPhone(_("Enter a mobile number that can receive messages."), code="not_mobile")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
