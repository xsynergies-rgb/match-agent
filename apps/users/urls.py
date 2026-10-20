from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("password/change/", views.PasswordChangeView.as_view(), name="password-change"),
    # Sign-in by one-time code: 404 while PHONE_CODES_ENABLED is off.
    path("phone/request/", views.PhoneCodeRequestView.as_view(), name="phone-request"),
    path("phone/verify/", views.PhoneCodeVerifyView.as_view(), name="phone-verify"),
    path("refresh/", views.RefreshView.as_view(), name="token-refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
]
