"""Booking rules. Every change that depends on how many spots are left locks the match row first,
so two owners confirming at once, or a confirmation racing a capacity change, can't overfill it.
"""

import datetime

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError

from common.exceptions import Conflict

from .models import Match, Pitch, Reservation

Status = Reservation.Status


# --- reading ---------------------------------------------------------------------------------


def bookable_matches(*, city=None, date=None, pitch_ids=None):
    matches = Match.objects.bookable().select_related("pitch")
    if city:
        matches = matches.filter(pitch__city__iexact=city)
    if date:
        matches = matches.filter(date=date)
    else:
        matches = matches.filter(date__lte=timezone.localdate() + datetime.timedelta(days=settings.BOOKING_WINDOW_DAYS))
    if pitch_ids:
        matches = matches.filter(pitch_id__in=pitch_ids)
    return matches.order_by("date", "start_time", "pitch__city", "pitch__name")[:500]


def reservations_with_matches(queryset):
    """Bookings with their match (and its spot counts) and pitch, in two queries."""
    return queryset.prefetch_related(
        Prefetch("match", queryset=Match.objects.with_counts().select_related("pitch"))
    ).select_related("player")


def owned_pitches(user):
    pitches = Pitch.objects.filter(is_active=True)
    return pitches if user.is_staff else pitches.filter(owner=user)


def owner_reservations(user, *, status=None):
    reservations = Reservation.objects.filter(match__pitch__in=owned_pitches(user))
    if status:
        reservations = reservations.filter(status=status)
    return reservations_with_matches(reservations).order_by("created_at")


def owner_matches(user, *, date=None, pitch_id=None):
    matches = Match.objects.with_counts().select_related("pitch").filter(pitch__in=owned_pitches(user))
    if date:
        matches = matches.filter(date=date)
    if pitch_id:
        matches = matches.filter(pitch_id=pitch_id)
    return matches.order_by("date", "start_time", "pitch__name")[:500]


def match_with_counts(match_id):
    return Match.objects.with_counts().select_related("pitch").get(pk=match_id)


def reservation_with_match(reservation_id):
    return reservations_with_matches(Reservation.objects.filter(pk=reservation_id)).get()


# --- players ---------------------------------------------------------------------------------


def _lock_match(match_id):
    try:
        return Match.objects.select_for_update(of=("self",)).select_related("pitch").get(pk=match_id)
    except Match.DoesNotExist:
        raise NotFound(_("This match doesn't exist.")) from None


@transaction.atomic
def create_reservation(*, player, match_id):
    """Ask for a spot. Returns ``(reservation, created)``; asking again returns the same booking."""
    if not player.profile_complete:
        raise ValidationError(_("Complete your profile before booking."), code="profile_incomplete")

    match = _lock_match(match_id)
    existing = match.reservations.filter(player=player, status__in=Reservation.ACTIVE).first()
    if existing:
        return existing, False

    if (
        not match.is_open
        or not match.pitch.is_active
        or match.has_started()
        or match.confirmed_bookings() >= match.capacity
    ):
        raise Conflict(_("This match is no longer available."), code="match_unavailable")

    limit = settings.BOOKING_MAX_PENDING_PER_PLAYER
    if Reservation.objects.filter(player=player, status=Status.PENDING).count() >= limit:
        raise Conflict(
            _("You already have %(limit)d bookings waiting for confirmation.") % {"limit": limit},
            code="too_many_pending",
        )

    try:
        with transaction.atomic():
            return Reservation.objects.create(match=match, player=player), True
    except IntegrityError:
        # The same player asked twice at the same moment; hand back the booking that won.
        return match.reservations.get(player=player, status__in=Reservation.ACTIVE), False


@transaction.atomic
def cancel_reservation(*, player, reservation_id):
    try:
        reservation = (
            Reservation.objects.select_for_update(of=("self",))
            .select_related("match")
            .get(pk=reservation_id, player=player)
        )
    except Reservation.DoesNotExist:
        raise NotFound(_("This booking doesn't exist.")) from None
    if reservation.status not in Reservation.ACTIVE or reservation.match.has_started():
        raise Conflict(_("This booking can no longer be cancelled."), code="not_cancellable")
    reservation.status = Status.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])
    return reservation


# --- pitch owners ----------------------------------------------------------------------------


def _lock_owned_reservation(owner, reservation_id):
    try:
        return (
            Reservation.objects.select_for_update(of=("self",))
            .select_related("match")
            .get(pk=reservation_id, match__pitch__in=owned_pitches(owner))
        )
    except Reservation.DoesNotExist:
        raise NotFound(_("This booking doesn't exist.")) from None


def _decide(reservation, owner, status):
    reservation.status = status
    reservation.decided_at = timezone.now()
    reservation.decided_by = owner
    reservation.save(update_fields=["status", "decided_at", "decided_by", "updated_at"])


@transaction.atomic
def confirm_reservation(*, owner, reservation_id):
    reservation = _lock_owned_reservation(owner, reservation_id)
    if reservation.status != Status.PENDING:
        raise Conflict(_("This booking has already been handled."), code="not_pending")
    match = _lock_match(reservation.match_id)
    if match.confirmed_bookings() >= match.capacity:
        raise Conflict(_("This match is already full."), code="match_full")
    _decide(reservation, owner, Status.CONFIRMED)
    return reservation


@transaction.atomic
def decline_reservation(*, owner, reservation_id):
    reservation = _lock_owned_reservation(owner, reservation_id)
    if reservation.status != Status.PENDING:
        raise Conflict(_("This booking has already been handled."), code="not_pending")
    _decide(reservation, owner, Status.DECLINED)
    return reservation


@transaction.atomic
def create_match(*, owner, pitch_id, date, start_time, end_time, capacity):
    pitch = owned_pitches(owner).filter(pk=pitch_id).first()
    if pitch is None:
        raise NotFound(_("This pitch doesn't exist."))
    if end_time <= start_time:
        raise ValidationError({"end_time": [_("The match must end after it starts.")]}, code="invalid")
    if date < timezone.localdate():
        raise ValidationError({"date": [_("Pick today or a later date.")]}, code="invalid")
    overlapping = Match.objects.filter(pitch=pitch, date=date, start_time__lt=end_time, end_time__gt=start_time)
    if overlapping.exists():
        raise ValidationError(_("This pitch already has a match at that time."), code="overlap")
    try:
        with transaction.atomic():
            match = Match.objects.create(
                pitch=pitch, date=date, start_time=start_time, end_time=end_time, capacity=capacity
            )
    except IntegrityError:
        raise ValidationError(_("This pitch already has a match at that time."), code="overlap") from None
    return match


@transaction.atomic
def update_match(*, owner, match_id, capacity=None, is_open=None):
    try:
        match = Match.objects.select_for_update().get(pk=match_id, pitch__in=owned_pitches(owner))
    except Match.DoesNotExist:
        raise NotFound(_("This match doesn't exist.")) from None
    fields = []
    if capacity is not None:
        if capacity < match.confirmed_bookings():
            raise ValidationError(
                {"capacity": [_("More players are already confirmed than that.")]}, code="capacity_below_confirmed"
            )
        match.capacity = capacity
        fields.append("capacity")
    if is_open is not None:
        match.is_open = is_open
        fields.append("is_open")
    if fields:
        match.save(update_fields=fields)
    return match
