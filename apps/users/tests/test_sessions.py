from django.urls import reverse

from apps.users import services
from apps.users.models import User
from common.testing import PASSWORD, ApiTestCase


class ProfileTests(ApiTestCase):
    def test_profile_needs_a_signed_in_user(self):
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)

    def test_new_account_completes_its_profile(self):
        user = self.make_user(complete=False)
        self.sign_in_as(user)
        me = self.client.get(reverse("me")).json()
        self.assertEqual(me["phone"], "+212612345678")
        self.assertFalse(me["profile_complete"])
        self.assertFalse(me["is_pitch_owner"])

        response = self.client.patch(
            reverse("me"), {"name": "  Salma   B ", "age_range": "18_24", "gender": "female", "phone": "+212700000000"}
        )
        self.assertEqual(response.status_code, 200)
        me = response.json()
        self.assertEqual(me["name"], "Salma B")
        self.assertTrue(me["profile_complete"])
        self.assertEqual(me["phone"], "+212612345678")  # read-only

    def test_profile_values_are_checked(self):
        self.sign_in_as(self.make_user())
        self.assertEqual(self.client.patch(reverse("me"), {"age_range": "18-24"}).status_code, 400)
        self.assertEqual(self.client.patch(reverse("me"), {"name": " "}).status_code, 400)


class TokenTests(ApiTestCase):
    def refresh(self, token):
        return self.client.post(reverse("token-refresh"), {"refresh": token})

    def test_refresh_hands_out_a_new_token_and_retires_the_old_one(self):
        tokens = services.issue_tokens(self.make_user())
        response = self.refresh(tokens["refresh"])
        self.assertEqual(response.status_code, 200)
        rotated = response.json()["refresh"]
        self.assertNotEqual(rotated, tokens["refresh"])
        self.assertEqual(self.refresh(tokens["refresh"]).status_code, 401)
        self.assertEqual(self.refresh(rotated).status_code, 200)

    def test_logout_retires_the_session(self):
        user = self.make_user()
        tokens = self.sign_in_as(user)
        self.assertEqual(self.client.post(reverse("logout"), {"refresh": tokens["refresh"]}).status_code, 204)
        self.assertEqual(self.refresh(tokens["refresh"]).status_code, 401)

    def test_logout_refuses_someone_elses_session(self):
        other = services.issue_tokens(self.make_user("+212612345679"))
        self.sign_in_as(self.make_user())
        self.assertEqual(self.client.post(reverse("logout"), {"refresh": other["refresh"]}).status_code, 400)
        self.assertEqual(self.refresh(other["refresh"]).status_code, 200)

    def test_deleting_the_account_ends_every_session(self):
        user = self.make_user()
        first = services.issue_tokens(user)
        rotated = self.refresh(first["refresh"]).json()["refresh"]
        tokens = self.sign_in_as(user)

        wrong = self.client.delete(reverse("me"), {"password": "not-my-password"})
        self.assertEqual(wrong.json()["code"], "wrong_password")
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

        self.assertEqual(self.client.delete(reverse("me"), {"password": PASSWORD}).status_code, 204)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)
        for token in [rotated, tokens["refresh"]]:
            self.assertEqual(self.refresh(token).status_code, 401)

    def test_removing_access_locks_the_account_out(self):
        user = self.make_user()
        tokens = self.sign_in_as(user)
        services.remove_access(user)
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)
        self.assertEqual(self.refresh(tokens["refresh"]).status_code, 401)
