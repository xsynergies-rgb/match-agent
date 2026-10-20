from rest_framework import serializers

from .models import Match, Pitch, Reservation


class PitchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pitch
        fields = ["id", "city", "name"]


class MatchSerializer(serializers.ModelSerializer):
    pitch = PitchSerializer(read_only=True)
    spots_left = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = ["id", "date", "start_time", "end_time", "capacity", "spots_left", "pitch"]

    def get_spots_left(self, match) -> int:
        spots = getattr(match, "spots_left", None)
        return spots if spots is not None else match.capacity - match.confirmed_bookings()


class OwnerMatchSerializer(MatchSerializer):
    confirmed_count = serializers.IntegerField(read_only=True)
    pending_count = serializers.IntegerField(read_only=True)

    class Meta(MatchSerializer.Meta):
        fields = MatchSerializer.Meta.fields + ["is_open", "confirmed_count", "pending_count"]


class BookedPitchSerializer(PitchSerializer):
    """A pitch inside the player's own booking: adds the number to message about it."""

    phone = serializers.SerializerMethodField()

    class Meta(PitchSerializer.Meta):
        fields = PitchSerializer.Meta.fields + ["phone"]

    def get_phone(self, pitch) -> str | None:
        return pitch.phone or None


class BookedMatchSerializer(MatchSerializer):
    pitch = BookedPitchSerializer(read_only=True)


class ReservationSerializer(serializers.ModelSerializer):
    # Only someone with a booking sees the pitch's number; the public lists don't show it.
    match = BookedMatchSerializer(read_only=True)

    class Meta:
        model = Reservation
        fields = ["id", "status", "created_at", "match"]


class PlayerSerializer(serializers.Serializer):
    name = serializers.CharField()
    phone = serializers.CharField()
    age_range = serializers.CharField()
    gender = serializers.CharField()


class OwnerReservationSerializer(ReservationSerializer):
    player = PlayerSerializer(read_only=True)

    class Meta(ReservationSerializer.Meta):
        fields = ReservationSerializer.Meta.fields + ["player"]


class MatchFilterSerializer(serializers.Serializer):
    city = serializers.CharField(required=False, max_length=60)
    date = serializers.DateField(required=False)
    pitch = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, max_length=50)


class ReservationCreateSerializer(serializers.Serializer):
    match = serializers.IntegerField(min_value=1)


class OwnerMatchCreateSerializer(serializers.Serializer):
    pitch = serializers.IntegerField(min_value=1)
    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    capacity = serializers.IntegerField(min_value=1, max_value=30, default=10)


class OwnerMatchUpdateSerializer(serializers.Serializer):
    capacity = serializers.IntegerField(min_value=1, max_value=30, required=False)
    is_open = serializers.BooleanField(required=False)
