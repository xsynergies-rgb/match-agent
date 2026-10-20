from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import APIException

from . import services
from .models import Match, Pitch, Reservation


@admin.register(Pitch)
class PitchAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "phone", "owner", "is_active"]
    fields = ["city", "name", "phone", "owner", "is_active"]
    list_filter = ["city", "is_active"]
    search_fields = ["name", "city"]
    autocomplete_fields = ["owner"]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ["pitch", "date", "start_time", "end_time", "capacity", "booked", "is_open"]
    list_filter = ["pitch__city", "pitch", "is_open"]
    date_hierarchy = "date"
    search_fields = ["pitch__name", "pitch__city"]
    list_select_related = ["pitch"]

    def get_queryset(self, request):
        return super().get_queryset(request).with_counts()

    @admin.display(description=_("confirmed"), ordering="confirmed_count")
    def booked(self, match):
        return f"{match.confirmed_count} / {match.capacity}"


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ["player", "match", "status", "created_at", "decided_by"]
    list_filter = ["status", "match__pitch__city", "match__pitch"]
    search_fields = ["player__phone", "player__name", "match__pitch__name"]
    list_select_related = ["player", "match__pitch", "decided_by"]
    autocomplete_fields = ["player"]
    raw_id_fields = ["match"]
    # Status changes go through the actions, which apply the same rules as the API (capacity).
    readonly_fields = ["status", "decided_at", "decided_by", "created_at", "updated_at"]
    actions = ["confirm", "decline"]

    def _apply(self, request, queryset, action, done_message):
        done = 0
        for reservation in queryset:
            try:
                action(owner=request.user, reservation_id=reservation.pk)
                done += 1
            except APIException as error:
                self.message_user(request, f"{reservation}: {error.detail}", messages.WARNING)
        if done:
            self.message_user(request, done_message % {"count": done}, messages.SUCCESS)

    @admin.action(description=_("Confirm selected bookings"))
    def confirm(self, request, queryset):
        self._apply(request, queryset, services.confirm_reservation, _("%(count)d booking(s) confirmed."))

    @admin.action(description=_("Decline selected bookings"))
    def decline(self, request, queryset):
        self._apply(request, queryset, services.decline_reservation, _("%(count)d booking(s) declined."))
