import datetime

from django.urls import reverse
from django.utils import timezone

from apps.booking.models import Match, Reservation
from common.testing import ApiTestCase


class OwnerTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.make_user("+212661000001", name="Agdal owner")
        self.other_owner = self.make_user("+212661000002", name="Riad owner")
        self.agdal = self.make_pitch("Agdal", owner=self.owner)
        self.riad = self.make_pitch("Hay Riad", owner=self.other_owner)
        self.match = self.make_match(self.agdal, capacity=1)
        self.player = self.make_user("+212612345678", name="Karim")
        self.request = Reservation.objects.create(match=self.match, player=self.player)
        self.elsewhere = Reservation.objects.create(match=self.make_match(self.riad), player=self.player)
        self.sign_in_as(self.owner)

    def confirm(self, reservation):
        return self.client.post(reverse("owner-reservation-confirm", args=[reservation.id]))

    def test_players_are_not_owners(self):
        self.sign_in_as(self.player)
        self.assertFalse(self.client.get(reverse("me")).json()["is_pitch_owner"])
        for name in ["owner-pitches", "owner-reservations", "owner-matches"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.confirm(self.request).status_code, 403)

    def test_owners_see_requests_for_their_own_pitches_only(self):
        self.assertTrue(self.client.get(reverse("me")).json()["is_pitch_owner"])
        listed = self.client.get(reverse("owner-reservations"), {"status": "pending"}).json()
        self.assertEqual([r["id"] for r in listed], [str(self.request.id)])
        self.assertEqual(listed[0]["player"], {"name": "Karim", "phone": "+212612345678", "age_range": "25_34", "gender": "male"})
        self.assertEqual([p["name"] for p in self.client.get(reverse("owner-pitches")).json()], ["Agdal"])

    def test_confirming_takes_a_spot(self):
        response = self.confirm(self.request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "confirmed")
        self.assertEqual(response.json()["match"]["spots_left"], 0)
        self.request.refresh_from_db()
        self.assertEqual(self.request.decided_by, self.owner)
        self.assertEqual(self.confirm(self.request).json()["code"], "not_pending")

        # The player sees it, and the full match leaves the public list.
        self.sign_in_as(self.player)
        self.assertEqual(self.client.get(reverse("reservation", args=[self.request.id])).json()["status"], "confirmed")
        self.assertNotIn(self.match.id, [m["id"] for m in self.client.get(reverse("matches")).json()])

    def test_a_full_match_cannot_be_overfilled(self):
        late = Reservation.objects.create(match=self.match, player=self.make_user("+212612345679"))
        self.confirm(self.request)
        response = self.confirm(late)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "match_full")

    def test_declining(self):
        response = self.client.post(reverse("owner-reservation-decline", args=[self.request.id]))
        self.assertEqual(response.json()["status"], "declined")

    def test_another_owners_bookings_are_out_of_reach(self):
        self.assertEqual(self.confirm(self.elsewhere).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("owner-reservation-decline", args=[self.elsewhere.id])).status_code, 404
        )

    def test_staff_can_handle_every_pitch(self):
        self.sign_in_as(self.make_user("+212661000009", is_staff=True))
        self.assertEqual(self.confirm(self.elsewhere).status_code, 200)

    def test_owners_publish_slots_on_their_own_pitches(self):
        date = (timezone.localdate() + datetime.timedelta(days=5)).isoformat()
        slot = {"pitch": self.agdal.id, "date": date, "start_time": "20:00", "end_time": "21:30", "capacity": 12}
        created = self.client.post(reverse("owner-matches"), slot)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["spots_left"], 12)
        self.assertTrue(created.json()["is_open"])

        self.assertEqual(self.client.post(reverse("owner-matches"), slot).json()["code"], "overlap")
        overlapping = {**slot, "start_time": "21:00", "end_time": "22:00"}
        self.assertEqual(self.client.post(reverse("owner-matches"), overlapping).json()["code"], "overlap")
        backwards = {**slot, "start_time": "22:00", "end_time": "21:00"}
        self.assertEqual(self.client.post(reverse("owner-matches"), backwards).status_code, 400)
        past = {**slot, "date": "2020-01-01"}
        self.assertEqual(self.client.post(reverse("owner-matches"), past).status_code, 400)
        theirs = {**slot, "pitch": self.riad.id}
        self.assertEqual(self.client.post(reverse("owner-matches"), theirs).status_code, 404)

    def test_owners_adjust_and_close_slots(self):
        self.confirm(self.request)
        url = reverse("owner-match", args=[self.match.id])
        self.assertEqual(self.client.patch(url, {"capacity": 0}).status_code, 400)

        bigger = self.client.patch(url, {"capacity": 4})
        self.assertEqual(bigger.json()["spots_left"], 3)
        self.assertEqual(self.client.patch(url, {"is_open": False}).json()["is_open"], False)
        self.assertFalse(Match.objects.get(pk=self.match.id).is_open)

        other = reverse("owner-match", args=[self.elsewhere.match_id])
        self.assertEqual(self.client.patch(other, {"is_open": False}).status_code, 404)

    def test_capacity_cannot_drop_below_confirmed_players(self):
        self.client.patch(reverse("owner-match", args=[self.match.id]), {"capacity": 2})
        self.confirm(self.request)
        self.confirm(Reservation.objects.create(match=self.match, player=self.make_user("+212612345679")))
        response = self.client.patch(reverse("owner-match", args=[self.match.id]), {"capacity": 1})
        self.assertEqual(response.json()["code"], "capacity_below_confirmed")
