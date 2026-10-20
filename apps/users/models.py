import uuid

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """A person who signs in with their phone. Players, pitch owners and staff are all users."""

    class AgeRange(models.TextChoices):
        UNDER_18 = "under_18", _("Under 18")
        FROM_18_TO_24 = "18_24", "18-24"
        FROM_25_TO_34 = "25_34", "25-34"
        FROM_35_TO_44 = "35_44", "35-44"
        FROM_45 = "45_plus", "45+"

    class Gender(models.TextChoices):
        MALE = "male", _("Male")
        FEMALE = "female", _("Female")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(_("phone"), max_length=20, unique=True, help_text=_("E.164, e.g. +212612345678"))
    name = models.CharField(_("name"), max_length=80, blank=True)
    age_range = models.CharField(_("age range"), max_length=10, choices=AgeRange.choices, blank=True)
    gender = models.CharField(_("gender"), max_length=10, choices=Gender.choices, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("staff"), default=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.phone})" if self.name else self.phone

    def save(self, *args, **kwargs):
        # set_password() leaves the raw password in _password until the next save. Whatever
        # changed it - the app, the admin, `changepassword` - every session ends with it.
        password_changed = self._password is not None and not self._state.adding
        super().save(*args, **kwargs)
        if password_changed:
            from .services import end_all_sessions

            end_all_sessions(self)

    @property
    def profile_complete(self):
        return bool(self.name and self.age_range and self.gender)

    @property
    def is_pitch_owner(self):
        return self.is_staff or self.owned_pitches.exists()


class PhoneCode(models.Model):
    """A one-time sign-in code sent to a phone.

    Only a keyed hash of the code is stored: six digits are quick to try offline, so a plain
    hash in a leaked database would give the codes away; the key (SECRET_KEY) prevents that.
    A code works once, for a few minutes, and stops working after a few wrong tries.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=20)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["phone", "-created_at"], name="phonecode_phone_recent")]

    def __str__(self):
        return f"Code for {self.phone} at {self.created_at:%Y-%m-%d %H:%M}"
