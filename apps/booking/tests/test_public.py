import datetime

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.booking.models import Reservation
from common.testing import ApiTestCase


class PublicListTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.agdal = self.make_pitch("Agdal", "Rabat")
        self.riad = self.make_pitch("Hay Riad", "Rabat")
        self.maarif = self.make_pitch("Maarif", "Casablanca")
        self.closed_pitch = self.make_pitch("Old Field", "Rabat", is_active=False)

    def ids(self, response):
        self.assertEqual(response.status_code, 200)
        return [item["id"] for item in response.json()]

    def test_pitches_are_public(self):
        names = [p["name"] for p in self.client.get(reverse("pitches")).json()]
        self.assertEqual(names, ["Maarif", "Agdal", "Hay Riad"])  # by city, then name; inactive hidden
        rabat = self.client.get(reverse("pitches"), {"city": "rabat"}).json()
        self.assertEqual([p["name"] for p in rabat], ["Agdal", "Hay Riad"])

    def test_only_bookable_matches_are_listed(self):
        open_match = self.make_match(self.agdal)
        self.make_match(self.agdal, hour=19, is_open=False)
        self.make_match(self.closed_pitch)
        self.make_match(self.agdal, days_ahead=-1)
        full = self.make_match(self.riad, capacity=1)
        Reservation.objects.create(match=full, player=self.make_user(), status="confirmed")
        started = self.make_match(self.riad, days_ahead=0, hour=0)  # midnight today: already started
        self.assertEqual(self.ids(self.client.get(reverse("matches"))), [open_match.id])
        self.assertNotIn(started.id, self.ids(self.client.get(reverse("matches"))))

    def test_spots_left_count_confirmed_bookings_only(self):
        match = self.make_match(self.agdal, capacity=10)
        Reservation.objects.create(match=match, player=self.make_user(), status="confirmed")
        Reservation.objects.create(match=match, player=self.make_user("+212612345679"), status="pending")
        Reservation.objects.create(match=match, player=self.make_user("+212612345670"), status="declined")
        [listed] = self.client.get(reverse("matches")).json()
        self.assertEqual(listed["spots_left"], 9)
        self.assertEqual(listed["start_time"], "18:00")
        self.assertEqual(listed["pitch"], {"id": self.agdal.id, "city": "Rabat", "name": "Agdal"})

    def test_matches_can_be_filtered(self):
        tomorrow = self.make_match(self.agdal)
        later = self.make_match(self.riad, days_ahead=2)
        casa = self.make_match(self.maarif)
        date = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        self.assertEqual(self.ids(self.client.get(reverse("matches"), {"city": "Rabat"})), [tomorrow.id, later.id])
        self.assertEqual(self.ids(self.client.get(reverse("matches"), {"date": date})), [casa.id, tomorrow.id])
        both = self.client.get(reverse("matches"), {"pitch": [self.riad.id, self.maarif.id]})
        self.assertEqual(self.ids(both), [casa.id, later.id])

    def test_far_future_matches_need_an_explicit_date(self):
        far = self.make_match(self.agdal, days_ahead=30)
        self.assertEqual(self.ids(self.client.get(reverse("matches"))), [])
        self.assertEqual(self.ids(self.client.get(reverse("matches"), {"date": far.date.isoformat()})), [far.id])

    def test_a_bad_filter_is_a_clear_error(self):
        response = self.client.get(reverse("matches"), {"date": "next friday"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("date", response.json()["errors"])

    def test_a_stale_token_does_not_break_public_lists(self):
        self.make_match(self.agdal)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired.or.garbage")
        self.assertEqual(self.client.get(reverse("matches")).status_code, 200)
        self.assertEqual(self.client.get(reverse("pitches")).status_code, 200)


class PitchNumberTests(ApiTestCase):
    def test_the_number_is_stored_in_one_form(self):
        pitch = self.make_pitch(phone="06 61 23 45 67")
        pitch.full_clean()
        self.assertEqual(pitch.phone, "+212661234567")

    def test_a_wrong_number_is_refused(self):
        pitch = self.make_pitch(phone="12345")
        with self.assertRaises(ValidationError) as caught:
            pitch.full_clean()
        self.assertIn("phone", caught.exception.message_dict)
