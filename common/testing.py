"""Helpers shared by the test suites."""

import datetime

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.booking.models import Match, Pitch
from apps.users import services as user_services
from apps.users.models import User
from apps.users.senders import MemorySender


PASSWORD = "kickoff-at-agdal"


class ApiTestCase(APITestCase):
    def setUp(self):
        super().setUp()
        cache.clear()  # throttle counters live in the cache
        MemorySender.outbox.clear()

    # --- people ---------------------------------------------------------------------------

    def make_user(self, phone="+212612345678", *, complete=True, password=PASSWORD, **fields):
        if complete:
            fields = {"name": "Youssef", "age_range": "25_34", "gender": "male", **fields}
        return User.objects.create_user(phone, password, **fields)

    def sign_in_as(self, user):
        tokens = user_services.issue_tokens(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        return tokens

    def sign_out(self):
        self.client.credentials()

    def request_code(self, phone="0612345678"):
        response = self.client.post(reverse("phone-request"), {"phone": phone})
        code = MemorySender.outbox[-1]["code"] if MemorySender.outbox else None
        return response, code

    # --- pitches and matches --------------------------------------------------------------

    def make_pitch(self, name="Agdal", city="Rabat", **fields):
        return Pitch.objects.create(name=name, city=city, **fields)

    def make_match(self, pitch, *, days_ahead=1, hour=18, capacity=10, **fields):
        return Match.objects.create(
            pitch=pitch,
            date=timezone.localdate() + datetime.timedelta(days=days_ahead),
            start_time=datetime.time(hour),
            end_time=datetime.time(hour + 1),
            capacity=capacity,
            **fields,
        )
