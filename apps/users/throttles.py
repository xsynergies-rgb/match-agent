from common.throttles import AddressThrottle, IdentifierThrottle, ScopedUserThrottle

from .phone import InvalidPhone, normalize_phone


class PhoneThrottle(IdentifierThrottle):
    """Counts per phone number, in its normalised form, however it was typed."""

    identifier_field = "phone"

    def normalize(self, value):
        try:
            return normalize_phone(value)
        except InvalidPhone:
            return "".join(ch for ch in value if ch.isdigit())


class CodeRequestAddressThrottle(AddressThrottle):
    scope = "otp_request"


class CodeRequestPhoneThrottle(PhoneThrottle):
    scope = "otp_request_phone"


class CodeVerifyAddressThrottle(AddressThrottle):
    scope = "otp_verify"


class CodeVerifyPhoneThrottle(PhoneThrottle):
    scope = "otp_verify_phone"


class RefreshAddressThrottle(AddressThrottle):
    scope = "auth_refresh"


class RegisterAddressThrottle(AddressThrottle):
    scope = "auth_register"


class LoginAddressThrottle(AddressThrottle):
    scope = "auth_login"


class LoginPhoneThrottle(PhoneThrottle):
    scope = "auth_login_phone"


class PasswordChangeThrottle(ScopedUserThrottle):
    scope = "password_change"
