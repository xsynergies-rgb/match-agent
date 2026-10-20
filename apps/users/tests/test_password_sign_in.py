from unittest import mock

from django.urls import reverse

from apps.users.models import User
from apps.users.throttles import LoginPhoneThrottle
from common.testing import PASSWORD, ApiTestCase


class RegisterTests(ApiTestCase):
    def register(self, phone="06 12 34 56 78", password=PASSWORD):
        return self.client.post(reverse("register"), {"phone": phone, "password": password})

    def test_registering_signs_the_player_in(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["access"] and body["refresh"])
        self.assertTrue(body["is_new"])
        self.assertEqual(body["user"]["phone"], "+212612345678")
        self.assertFalse(body["user"]["profile_complete"])
        self.assertTrue(User.objects.get().check_password(PASSWORD))

    def test_one_account_per_number_however_it_is_typed(self):
        self.register("0612345678")
        response = self.register("+212 6 12 34 56 78")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "phone_taken")
        self.assertEqual(User.objects.count(), 1)

    def test_weak_passwords_are_refused(self):
        for weak in ["short", "12345678", "password"]:
            with self.subTest(password=weak):
                response = self.register(password=weak)
                self.assertEqual(response.status_code, 400)
                self.assertIn("password", response.json()["errors"])
        self.assertFalse(User.objects.exists())

    def test_the_number_must_be_a_moroccan_mobile(self):
        self.assertEqual(self.register("+33612345678").json()["code"], "region_not_allowed")
        self.assertEqual(self.register("0522123456").json()["code"], "not_mobile")


class LoginTests(ApiTestCase):
    def login(self, phone="0612345678", password=PASSWORD, **extra):
        return self.client.post(reverse("login"), {"phone": phone, "password": password}, **extra)

    def test_signing_in_with_any_way_of_typing_the_number(self):
        user = self.make_user()
        for typed in ["0612345678", "+212 6 12 34 56 78", "00212612345678"]:
            with self.subTest(typed=typed):
                response = self.login(typed)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["user"]["id"], str(user.pk))
                self.assertFalse(response.json()["is_new"])

    def test_every_failure_gets_the_same_answer(self):
        self.make_user()
        self.make_user("+212612345679", is_active=False)
        failures = [
            self.login(password="wrong-password"),  # wrong password
            self.login("0700000000"),  # no account
            self.login("0612345679"),  # disabled account
            self.login("not a number"),
        ]
        for response in failures:
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["code"], "invalid_credentials")
        self.assertEqual(len({r.json()["message"] for r in failures}), 1)

    def test_guesses_per_number_are_limited_whatever_the_address(self):
        self.make_user()
        with mock.patch.object(LoginPhoneThrottle, "get_rate", return_value="3/hour"):
            statuses = [self.login(password="guess", REMOTE_ADDR=f"10.0.2.{i}").status_code for i in range(4)]
            # The right password from yet another address is refused too: the number is locked for now.
            statuses.append(self.login(REMOTE_ADDR="10.0.2.99").status_code)
        self.assertEqual(statuses, [401, 401, 401, 429, 429])


class PasswordChangeTests(ApiTestCase):
    def refresh(self, token):
        return self.client.post(reverse("token-refresh"), {"refresh": token})

    def change(self, current=PASSWORD, new="a-brand-new-secret"):
        return self.client.post(reverse("password-change"), {"current_password": current, "new_password": new})

    def test_changing_the_password_keeps_this_phone_and_ends_every_other_session(self):
        user = self.make_user()
        other_phone = self.client.post(reverse("login"), {"phone": "0612345678", "password": PASSWORD}).json()
        this_phone = self.sign_in_as(user)

        response = self.change()
        self.assertEqual(response.status_code, 200)
        fresh = response.json()

        # The old access token stops working at once, and old refresh tokens are retired.
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)
        for old in [this_phone["refresh"], other_phone["refresh"]]:
            self.assertEqual(self.refresh(old).status_code, 401)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {fresh['access']}")
        self.assertEqual(self.client.get(reverse("me")).status_code, 200)
        self.assertEqual(self.refresh(fresh["refresh"]).status_code, 200)

        self.sign_out()
        login = self.client.post(reverse("login"), {"phone": "0612345678", "password": "a-brand-new-secret"})
        self.assertEqual(login.status_code, 200)

    def test_the_current_password_is_required(self):
        self.sign_in_as(self.make_user())
        response = self.change(current="not-it")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "wrong_password")
        self.assertEqual(self.change(new="1234").status_code, 400)

    def test_an_admin_reset_also_ends_every_session(self):
        user = self.make_user()
        tokens = self.sign_in_as(user)
        user.set_password("set-by-the-organizer")  # what /admin/ and `changepassword` do
        user.save()
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)
        self.assertEqual(self.refresh(tokens["refresh"]).status_code, 401)

    def test_saving_a_profile_does_not_end_sessions(self):
        user = self.make_user()
        tokens = self.sign_in_as(user)
        self.client.patch(reverse("me"), {"name": "New Name"})
        self.assertEqual(self.refresh(tokens["refresh"]).status_code, 200)
