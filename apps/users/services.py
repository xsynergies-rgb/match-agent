"""Signing in with a phone code, sessions, and removing accounts. Views call these and stay thin."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import PermissionDenied, Throttled, ValidationError
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from common.exceptions import InvalidCredentials, ServiceUnavailable

from .models import PhoneCode, User
from .senders import SendError, get_sender


def _check_new_password(password, user):
    try:
        validate_password(password, user=user)
    except DjangoValidationError as error:
        raise ValidationError({"password": list(error.messages)}, code="weak_password") from None


@transaction.atomic
def register(phone, password):
    """Create a player account for a normalised phone, signed in straight away."""
    user = User(phone=phone)
    _check_new_password(password, user)
    if User.objects.filter(phone=phone).exists():
        raise ValidationError({"phone": [_("An account already exists for this number. Sign in instead.")]}, code="phone_taken")
    try:
        with transaction.atomic():
            user = User.objects.create_user(phone, password)
    except IntegrityError:
        raise ValidationError({"phone": [_("An account already exists for this number. Sign in instead.")]}, code="phone_taken") from None
    return user


def login(phone, password):
    """Return the user for a phone and password, or refuse with one answer for every failure.

    A wrong password, an unknown number and a disabled account all get the same reply, and
    Django's backend spends the same time hashing either way, so the answer leaks nothing.
    """
    user = authenticate(phone=phone, password=password)
    if user is None:
        raise InvalidCredentials()
    return user


def change_password(user, current_password, new_password):
    """Change the password and return a fresh session; every other session ends."""
    if not user.check_password(current_password):
        raise ValidationError({"current_password": [_("Your current password is incorrect.")]}, code="wrong_password")
    _check_new_password(new_password, user)
    user.set_password(new_password)
    user.save()  # ends every session (see User.save)
    return issue_tokens(user)


def _code_hash(phone, code):
    return hmac.new(settings.SECRET_KEY.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class IssuedCode:
    phone: str
    code: str
    channel: str
    expires_in: int
    resend_in: int


def request_code(phone, channel=None):
    """Send a new code to a normalised phone, by ``channel`` (default: the preferred one).

    Any earlier code for the phone stops working. The cooldown covers every channel, so
    "Send by SMS instead" can't be used to double the messages.
    """
    channel = channel or settings.OTP_CHANNELS[0]
    now = timezone.now()
    cooldown = settings.OTP_RESEND_COOLDOWN
    with transaction.atomic():
        latest = PhoneCode.objects.select_for_update().filter(phone=phone).order_by("-created_at").first()
        if latest and latest.created_at > now - cooldown:
            raise Throttled(
                wait=(latest.created_at + cooldown - now).total_seconds(),
                detail=_("Wait a moment before asking for another code."),
            )
        PhoneCode.objects.filter(phone=phone).filter(Q(used_at__isnull=False) | Q(expires_at__lte=now)).delete()
        PhoneCode.objects.filter(phone=phone, used_at__isnull=True).update(used_at=now)
        code = f"{secrets.randbelow(10**6):06d}"
        record = PhoneCode.objects.create(
            phone=phone, code_hash=_code_hash(phone, code), created_at=now, expires_at=now + settings.OTP_CODE_TTL
        )

    try:
        get_sender().send(phone, code, channel)
    except SendError:
        record.delete()  # so the person can ask again straight away
        raise ServiceUnavailable(_("We couldn't send the code. Try again in a moment."), code="send_failed")

    return IssuedCode(
        phone=phone,
        code=code,
        channel=channel,
        expires_in=int(settings.OTP_CODE_TTL.total_seconds()),
        resend_in=int(cooldown.total_seconds()),
    )


def verify_code(phone, code):
    """Check a code and return ``(user, is_new)``, creating the account on first sign-in.

    Every way a code can fail - wrong, expired, already used, too many tries, never sent - gets
    the same answer, so the response says nothing about which numbers have accounts.
    """
    now = timezone.now()
    user = None
    is_new = False
    with transaction.atomic():
        record = (
            PhoneCode.objects.select_for_update()
            .filter(phone=phone, used_at__isnull=True, expires_at__gt=now)
            .order_by("-created_at")
            .first()
        )
        if record is not None and record.attempts < settings.OTP_MAX_ATTEMPTS:
            if hmac.compare_digest(record.code_hash, _code_hash(phone, code)):
                record.used_at = now
                record.save(update_fields=["used_at"])
                user = User.objects.filter(phone=phone).first()
                if user is None:
                    user = User.objects.create_user(phone)
                    is_new = True
            else:
                # Saved before the refusal below, outside this block, so the try still counts.
                PhoneCode.objects.filter(pk=record.pk).update(attempts=F("attempts") + 1)

    if user is None:
        raise ValidationError(_("That code is wrong or has expired. Ask for a new one."), code="code_invalid")
    if not user.is_active:
        raise PermissionDenied(_("This account has been disabled."), code="account_disabled")
    return user, is_new


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    update_last_login(None, user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def logout(user, raw_refresh):
    """Retire one refresh token, which must belong to the signed-in user."""
    refused = ValidationError({"refresh": [_("This session is not valid.")]}, code="invalid")
    try:
        token = RefreshToken(raw_refresh)
    except TokenError:
        raise refused from None
    if str(token.get(jwt_settings.USER_ID_CLAIM)) != str(user.pk):
        raise refused
    token.blacklist()


def end_all_sessions(user):
    """Retire every refresh token the user holds. Access tokens die within 15 minutes."""
    outstanding = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in outstanding], ignore_conflicts=True
    )


@transaction.atomic
def delete_account(user, password):
    """Sign out everywhere, then delete the person and their bookings. Needs the password."""
    if not user.check_password(password):
        raise ValidationError({"password": [_("Your password is incorrect.")]}, code="wrong_password")
    end_all_sessions(user)
    user.delete()


@transaction.atomic
def remove_access(user):
    """Disable an account (admin action): no sign-in, no refresh, existing access tokens refused."""
    user.is_active = False
    user.save(update_fields=["is_active", "updated_at"])
    end_all_sessions(user)
