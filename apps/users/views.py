from django.conf import settings
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from . import services
from .serializers import (
    AccountDeleteSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    PhoneCodeRequestSerializer,
    PhoneCodeVerifySerializer,
    RefreshSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .throttles import (
    CodeRequestAddressThrottle,
    CodeRequestPhoneThrottle,
    CodeVerifyAddressThrottle,
    CodeVerifyPhoneThrottle,
    LoginAddressThrottle,
    LoginPhoneThrottle,
    PasswordChangeThrottle,
    RefreshAddressThrottle,
    RegisterAddressThrottle,
)


class PublicAuthView(APIView):
    # Public, and deliberately ignores any bearer token: a stale one must not block signing in.
    authentication_classes = []
    permission_classes = [permissions.AllowAny]


def _session(user, *, is_new):
    return {**services.issue_tokens(user), "user": UserSerializer(user).data, "is_new": is_new}


class RegisterView(PublicAuthView):
    throttle_classes = [RegisterAddressThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.register(serializer.validated_data["phone"], serializer.validated_data["password"])
        return Response(_session(user, is_new=True), status=status.HTTP_201_CREATED)


class LoginView(PublicAuthView):
    throttle_classes = [LoginAddressThrottle, LoginPhoneThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.login(serializer.validated_data["phone"], serializer.validated_data["password"])
        return Response(_session(user, is_new=False))


class PasswordChangeView(APIView):
    throttle_classes = [PasswordChangeThrottle]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tokens = services.change_password(
            request.user, serializer.validated_data["current_password"], serializer.validated_data["new_password"]
        )
        return Response(tokens)


class PhoneCodeView(PublicAuthView):
    """Sign-in by one-time code; answers 404 while PHONE_CODES_ENABLED is off."""

    def initial(self, request, *args, **kwargs):
        if not settings.PHONE_CODES_ENABLED:
            raise NotFound()
        super().initial(request, *args, **kwargs)


class PhoneCodeRequestView(PhoneCodeView):
    throttle_classes = [CodeRequestAddressThrottle, CodeRequestPhoneThrottle]

    def post(self, request):
        serializer = PhoneCodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issued = services.request_code(serializer.validated_data["phone"], serializer.validated_data.get("channel"))
        body = {
            "phone": issued.phone,
            "channel": issued.channel,
            "channels": settings.OTP_CHANNELS,
            "expires_in": issued.expires_in,
            "resend_in": issued.resend_in,
        }
        if settings.OTP_DEBUG_RESPONSE:
            body["debug_code"] = issued.code
        return Response(body, status=status.HTTP_202_ACCEPTED)


class PhoneCodeVerifyView(PhoneCodeView):
    throttle_classes = [CodeVerifyAddressThrottle, CodeVerifyPhoneThrottle]

    def post(self, request):
        serializer = PhoneCodeVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, is_new = services.verify_code(serializer.validated_data["phone"], serializer.validated_data["code"])
        return Response(_session(user, is_new=is_new))


class RefreshView(TokenRefreshView):
    serializer_class = RefreshSerializer
    throttle_classes = [RefreshAddressThrottle]


class LogoutView(APIView):
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.logout(request.user, serializer.validated_data["refresh"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        serializer = AccountDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.delete_account(request.user, serializer.validated_data["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)
