from unittest import mock

from django.urls import reverse

from apps.booking.models import Reservation
from apps.booking.views import ReservationCreateThrottle
from common.testing import ApiTestCase


class ReservationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.pitch = self.make_pitch()
        self.match = self.make_match(self.pitch, capacity=2)
        self.player = self.make_user()
        self.sign_in_as(self.player)

    def book(self, match=None):
        return self.client.post(reverse("reservations"), {"match": (match or self.match).id})

    def test_booking_needs_a_signed_in_player(self):
        self.sign_out()
        self.assertEqual(self.book().status_code, 401)

    def test_booking_needs_a_complete_profile(self):
        self.sign_in_as(self.make_user("+212612345679", complete=False))
        response = self.book()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "profile_incomplete")

    def test_booking_creates_a_pending_request_once(self):
        first = self.book()
        self.assertEqual(first.status_code, 201)
        body = first.json()
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["match"]["id"], self.match.id)
        self.assertEqual(body["match"]["spots_left"], 2)

        again = self.book()
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["id"], body["id"])
        self.assertEqual(Reservation.objects.count(), 1)

    def test_unavailable_matches_are_refused(self):
        self.match.is_open = False
        self.match.save()
        self.assertEqual(self.book().json()["code"], "match_unavailable")
        self.assertEqual(self.client.post(reverse("reservations"), {"match": 999999}).status_code, 404)

    def test_a_full_match_is_refused(self):
        for phone in ["+212612345679", "+212612345670"]:
            Reservation.objects.create(match=self.match, player=self.make_user(phone), status="confirmed")
        response = self.book()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "match_unavailable")

    def test_pending_requests_are_capped(self):
        for hour in range(16, 21):
            self.assertEqual(self.book(self.make_match(self.pitch, hour=hour, days_ahead=2)).status_code, 201)
        response = self.book()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "too_many_pending")

    def test_players_only_see_their_own_bookings(self):
        mine = self.book().json()
        other = self.make_user("+212612345679")
        theirs = Reservation.objects.create(match=self.match, player=other)

        listed = self.client.get(reverse("reservations")).json()
        self.assertEqual([r["id"] for r in listed], [mine["id"]])
        self.assertEqual(self.client.get(reverse("reservation", args=[mine["id"]])).status_code, 200)
        self.assertEqual(self.client.get(reverse("reservation", args=[theirs.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse("reservation-cancel", args=[theirs.id])).status_code, 404)

    def test_a_booking_shows_the_pitch_number_but_public_lists_do_not(self):
        self.assertIsNone(self.book().json()["match"]["pitch"]["phone"])

        self.pitch.phone = "+212661234567"
        self.pitch.save()
        booking = self.client.get(reverse("reservations")).json()[0]
        self.assertEqual(booking["match"]["pitch"]["phone"], "+212661234567")
        self.sign_out()
        self.assertNotIn("phone", self.client.get(reverse("matches")).json()[0]["pitch"])
        self.assertNotIn("phone", self.client.get(reverse("pitches")).json()[0])

    def test_cancelling_frees_the_spot_and_allows_booking_again(self):
        booking = self.book().json()
        Reservation.objects.filter(pk=booking["id"]).update(status="confirmed")
        cancel = self.client.post(reverse("reservation-cancel", args=[booking["id"]]))
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(cancel.json()["status"], "cancelled")
        self.assertEqual(cancel.json()["match"]["spots_left"], 2)

        again = self.client.post(reverse("reservation-cancel", args=[booking["id"]]))
        self.assertEqual(again.json()["code"], "not_cancellable")
        self.assertEqual(self.book().status_code, 201)

    def test_booking_requests_per_player_are_limited(self):
        with mock.patch.object(ReservationCreateThrottle, "get_rate", return_value="2/hour"):
            statuses = [self.book(self.make_match(self.pitch, hour=h, days_ahead=3)).status_code for h in (16, 17, 18)]
        self.assertEqual(statuses, [201, 201, 429])
