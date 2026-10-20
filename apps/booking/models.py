import datetime
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.users.phone import InvalidPhone, normalize_phone


class Pitch(models.Model):
    city = models.CharField(_("city"), max_length=60)
    name = models.CharField(_("name"), max_length=80)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("owner"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_pitches",
        help_text=_("Confirms or declines bookings and publishes slots for this pitch."),
    )
    phone = models.CharField(
        _("WhatsApp number"),
        max_length=16,
        blank=True,
        help_text=_(
            "Players who booked here message this number from the app. "
            "Leave empty to use the main organizer's number."
        ),
    )
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "pitches"
        ordering = ["city", "name"]
        constraints = [models.UniqueConstraint(fields=["city", "name"], name="unique_pitch_per_city")]

    def __str__(self):
        return f"{self.name} ({self.city})"

    def clean(self):
        # Stored in E.164 ("+212612345678") however it was typed, so WhatsApp links work.
        if self.phone:
            try:
                self.phone = normalize_phone(self.phone)
            except InvalidPhone:
                raise ValidationError(
                    {"phone": _("Enter a Moroccan mobile number that has WhatsApp, e.g. 06 12 34 56 78.")}
                ) from None


class MatchQuerySet(models.QuerySet):
    def with_counts(self):
        """Annotate confirmed and pending bookings, and the spots still free."""
        confirmed = Q(reservations__status=Reservation.Status.CONFIRMED)
        pending = Q(reservations__status=Reservation.Status.PENDING)
        return self.annotate(
            confirmed_count=Count("reservations", filter=confirmed),
            pending_count=Count("reservations", filter=pending),
        ).annotate(spots_left=F("capacity") - F("confirmed_count"))

    def not_started(self):
        now = timezone.localtime()
        return self.filter(Q(date__gt=now.date()) | Q(date=now.date(), start_time__gt=now.time()))

    def bookable(self):
        """What a player may ask to join: open, on an active pitch, not started, with a free spot."""
        return self.with_counts().not_started().filter(is_open=True, pitch__is_active=True, spots_left__gt=0)


class Match(models.Model):
    """One time slot on one pitch, which players book spots in."""

    pitch = models.ForeignKey(Pitch, on_delete=models.CASCADE, related_name="matches")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    capacity = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(1), MaxValueValidator(30)]
    )
    is_open = models.BooleanField(_("open for booking"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MatchQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "matches"
        ordering = ["date", "start_time"]
        constraints = [
            models.UniqueConstraint(fields=["pitch", "date", "start_time"], name="unique_slot_per_pitch"),
            models.CheckConstraint(condition=Q(end_time__gt=F("start_time")), name="match_ends_after_start"),
            models.CheckConstraint(condition=Q(capacity__gte=1), name="match_has_capacity"),
        ]

    def __str__(self):
        return f"{self.pitch} {self.date} {self.start_time:%H:%M}-{self.end_time:%H:%M}"

    @property
    def starts_at(self):
        return timezone.make_aware(datetime.datetime.combine(self.date, self.start_time))

    def has_started(self):
        return self.starts_at <= timezone.now()

    def confirmed_bookings(self):
        return self.reservations.filter(status=Reservation.Status.CONFIRMED).count()


class Reservation(models.Model):
    """A player's request for a spot in a match, which the pitch owner confirms or declines."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        DECLINED = "declined", _("Declined")
        CANCELLED = "cancelled", _("Cancelled")

    ACTIVE = (Status.PENDING, Status.CONFIRMED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="reservations")
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reservations")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # One live booking per player per match: asking twice returns the same booking.
            models.UniqueConstraint(
                fields=["match", "player"],
                condition=Q(status__in=["pending", "confirmed"]),
                name="one_active_booking_per_player_and_match",
            )
        ]

    def __str__(self):
        return f"{self.player} → {self.match} ({self.status})"
