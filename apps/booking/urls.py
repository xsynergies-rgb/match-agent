from django.urls import path

from . import views

urlpatterns = [
    path("pitches/", views.PitchListView.as_view(), name="pitches"),
    path("matches/", views.MatchListView.as_view(), name="matches"),
    path("reservations/", views.ReservationListView.as_view(), name="reservations"),
    path("reservations/<uuid:reservation_id>/", views.ReservationDetailView.as_view(), name="reservation"),
    path(
        "reservations/<uuid:reservation_id>/cancel/",
        views.ReservationCancelView.as_view(),
        name="reservation-cancel",
    ),
    path("owner/pitches/", views.OwnerPitchListView.as_view(), name="owner-pitches"),
    path("owner/reservations/", views.OwnerReservationListView.as_view(), name="owner-reservations"),
    path(
        "owner/reservations/<uuid:reservation_id>/confirm/",
        views.OwnerReservationConfirmView.as_view(),
        name="owner-reservation-confirm",
    ),
    path(
        "owner/reservations/<uuid:reservation_id>/decline/",
        views.OwnerReservationDeclineView.as_view(),
        name="owner-reservation-decline",
    ),
    path("owner/matches/", views.OwnerMatchListView.as_view(), name="owner-matches"),
    path("owner/matches/<int:match_id>/", views.OwnerMatchDetailView.as_view(), name="owner-match"),
]
