from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from .models import User
from .phone import InvalidPhone, normalize_phone


class PhoneField(serializers.CharField):
    """Accepts a phone number typed any common way; yields its E.164 form."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 32)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        raw = super().to_internal_value(data)
        try:
            return normalize_phone(raw)
        except InvalidPhone as error:
            raise serializers.ValidationError(error.message, code=error.code) from None


class PasswordField(serializers.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault("write_only", True)
        kwargs.setdefault("trim_whitespace", False)
        kwargs.setdefault("max_length", 128)
        super().__init__(**kwargs)


class RegisterSerializer(serializers.Serializer):
    phone = PhoneField()
    password = PasswordField()


class LoginSerializer(serializers.Serializer):
    # Not validated as a phone number: any failure must look the same (see services.login).
    phone = serializers.CharField(max_length=32)
    password = PasswordField()


class PasswordChangeSerializer(serializers.Serializer):
    current_password = PasswordField()
    new_password = PasswordField()


class AccountDeleteSerializer(serializers.Serializer):
    password = PasswordField()


class PhoneCodeRequestSerializer(serializers.Serializer):
    phone = PhoneField()
    channel = serializers.CharField(required=False, max_length=16)

    def validate_channel(self, value):
        if value not in settings.OTP_CHANNELS:
            raise serializers.ValidationError(_("Codes can't be sent that way right now."), code="channel_unavailable")
        return value


class PhoneCodeVerifySerializer(serializers.Serializer):
    phone = PhoneField()
    code = serializers.RegexField(
        r"^\d{6}$", error_messages={"invalid": _("Enter the 6-digit code from the message.")}
    )


class UserSerializer(serializers.ModelSerializer):
    profile_complete = serializers.BooleanField(read_only=True)
    is_pitch_owner = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "phone", "name", "age_range", "gender", "profile_complete", "is_pitch_owner"]
        read_only_fields = ["id", "phone"]

    def validate_name(self, value):
        value = " ".join(value.split())
        if len(value) < 2:
            raise serializers.ValidationError(_("Enter your name."))
        return value


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class RefreshSerializer(TokenRefreshSerializer):
    """SimpleJWT's refresh, refusing cleanly (401) when the token's user no longer exists."""

    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except get_user_model().DoesNotExist:
            raise AuthenticationFailed(_("No active account found for this session."), "no_active_account") from None
