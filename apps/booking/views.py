from rest_framework import permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from common.throttles import ScopedUserThrottle

from . import services
from .models import Pitch, Reservation
from .permissions import IsPitchOwner
from .serializers import (
    MatchFilterSerializer,
    MatchSerializer,
    OwnerMatchCreateSerializer,
    OwnerMatchSerializer,
    OwnerMatchUpdateSerializer,
    OwnerReservationSerializer,
    PitchSerializer,
    ReservationCreateSerializer,
    ReservationSerializer,
)


class ReservationCreateThrottle(ScopedUserThrottle):
    scope = "reservation_create"


class PublicView(APIView):
    # Public reads ignore any bearer token, so an expired one can't make them fail.
    authentication_classes = []
    permission_classes = [permissions.AllowAny]


# --- public ----------------------------------------------------------------------------------


class PitchListView(PublicView):
    def get(self, request):
        pitches = Pitch.objects.filter(is_active=True)
        city = request.query_params.get("city")
        if city:
            pitches = pitches.filter(city__iexact=city)
        return Response(PitchSerializer(pitches, many=True).data)


class MatchListView(PublicView):
    def get(self, request):
        filters = MatchFilterSerializer(
            data={**request.query_params.dict(), "pitch": request.query_params.getlist("pitch")}
        )
        filters.is_valid(raise_exception=True)
        data = filters.validated_data
        matches = services.bookable_matches(city=data.get("city"), date=data.get("date"), pitch_ids=data.get("pitch"))
        return Response(MatchSerializer(matches, many=True).data)


# --- players ---------------------------------------------------------------------------------


class ReservationListView(APIView):
    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method == "POST":
            throttles.append(ReservationCreateThrottle())
        return throttles

    def get(self, request):
        reservations = services.reservations_with_matches(request.user.reservations.all())[:100]
        return Response(ReservationSerializer(reservations, many=True).data)

    def post(self, request):
        serializer = ReservationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reservation, created = services.create_reservation(
            player=request.user, match_id=serializer.validated_data["match"]
        )
        body = ReservationSerializer(services.reservation_with_match(reservation.pk)).data
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ReservationDetailView(APIView):
    def get(self, request, reservation_id):
        reservation = services.reservations_with_matches(request.user.reservations.filter(pk=reservation_id)).first()
        if reservation is None:
            raise NotFound()
        return Response(ReservationSerializer(reservation).data)


class ReservationCancelView(APIView):
    def post(self, request, reservation_id):
        reservation = services.cancel_reservation(player=request.user, reservation_id=reservation_id)
        return Response(ReservationSerializer(services.reservation_with_match(reservation.pk)).data)


# --- pitch owners ----------------------------------------------------------------------------


class OwnerView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPitchOwner]


class OwnerPitchListView(OwnerView):
    def get(self, request):
        return Response(PitchSerializer(services.owned_pitches(request.user), many=True).data)


class OwnerReservationListView(OwnerView):
    def get(self, request):
        wanted = request.query_params.get("status")
        if wanted and wanted not in Reservation.Status.values:
            wanted = None
        reservations = services.owner_reservations(request.user, status=wanted)[:200]
        return Response(OwnerReservationSerializer(reservations, many=True).data)


class OwnerReservationConfirmView(OwnerView):
    def post(self, request, reservation_id):
        reservation = services.confirm_reservation(owner=request.user, reservation_id=reservation_id)
        return Response(OwnerReservationSerializer(services.reservation_with_match(reservation.pk)).data)


class OwnerReservationDeclineView(OwnerView):
    def post(self, request, reservation_id):
        reservation = services.decline_reservation(owner=request.user, reservation_id=reservation_id)
        return Response(OwnerReservationSerializer(services.reservation_with_match(reservation.pk)).data)


class OwnerMatchListView(OwnerView):
    def get(self, request):
        filters = MatchFilterSerializer(
            data={key: value for key, value in request.query_params.items() if key == "date"}
        )
        filters.is_valid(raise_exception=True)
        pitch = request.query_params.get("pitch", "")
        matches = services.owner_matches(
            request.user,
            date=filters.validated_data.get("date"),
            pitch_id=int(pitch) if pitch.isdigit() else None,
        )
        return Response(OwnerMatchSerializer(matches, many=True).data)

    def post(self, request):
        serializer = OwnerMatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        match = services.create_match(
            owner=request.user,
            pitch_id=data["pitch"],
            date=data["date"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            capacity=data["capacity"],
        )
        return Response(
            OwnerMatchSerializer(services.match_with_counts(match.pk)).data, status=status.HTTP_201_CREATED
        )


class OwnerMatchDetailView(OwnerView):
    def patch(self, request, match_id):
        serializer = OwnerMatchUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        match = services.update_match(owner=request.user, match_id=match_id, **serializer.validated_data)
        return Response(OwnerMatchSerializer(services.match_with_counts(match.pk)).data)
