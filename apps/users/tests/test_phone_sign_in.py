import datetime
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.users.models import PhoneCode, User
from apps.users.senders import MemorySender, SendError
from apps.users.throttles import CodeRequestPhoneThrottle, CodeVerifyPhoneThrottle
from common.testing import ApiTestCase

NO_COOLDOWN = override_settings(OTP_RESEND_COOLDOWN=datetime.timedelta(0))
CODES_ON = override_settings(PHONE_CODES_ENABLED=True)


class CodesSwitchTests(ApiTestCase):
    def test_code_sign_in_is_off_by_default(self):
        self.assertEqual(self.client.post(reverse("phone-request"), {"phone": "0612345678"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("phone-verify"), {"phone": "0612345678", "code": "123456"}).status_code, 404)
        self.assertEqual(MemorySender.outbox, [])


@CODES_ON
class RequestCodeTests(ApiTestCase):
    def test_sends_a_code_to_the_normalised_number(self):
        response, code = self.request_code("06 12 34 56 78")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            response.json(),
            {
                "phone": "+212612345678",
                "channel": "whatsapp",
                "channels": ["whatsapp", "sms"],
                "expires_in": 600,
                "resend_in": 30,
            },
        )
        self.assertEqual(MemorySender.outbox, [{"phone": "+212612345678", "code": code, "channel": "whatsapp"}])
        self.assertRegex(code, r"^\d{6}$")
        stored = PhoneCode.objects.get()
        self.assertNotIn(code, stored.code_hash)

    def test_every_way_of_typing_a_number_is_the_same_number(self):
        for typed in ["0612345678", "+212 6 12 34 56 78", "00212612345678", "212612345678"]:
            with self.subTest(typed=typed), NO_COOLDOWN:
                response, _ = self.request_code(typed)
                self.assertEqual(response.json()["phone"], "+212612345678")

    @override_settings(OTP_DEBUG_RESPONSE=True)
    def test_code_is_in_the_response_only_on_a_debug_server(self):
        response, code = self.request_code()
        self.assertEqual(response.json()["debug_code"], code)

    def test_refuses_numbers_that_cannot_be_used(self):
        cases = {"123": "invalid", "+33612345678": "region_not_allowed", "0522123456": "not_mobile", "": "blank"}
        for typed, code in cases.items():
            with self.subTest(typed=typed):
                response, _ = self.request_code(typed)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], code)
        self.assertEqual(MemorySender.outbox, [])

    def test_a_player_can_ask_for_another_channel(self):
        response = self.client.post(reverse("phone-request"), {"phone": "0612345678", "channel": "sms"})
        self.assertEqual(response.json()["channel"], "sms")
        self.assertEqual(MemorySender.outbox[-1]["channel"], "sms")

    @override_settings(OTP_CHANNELS=["sms"])
    def test_a_channel_that_is_not_offered_is_refused(self):
        response = self.client.post(reverse("phone-request"), {"phone": "0612345678", "channel": "whatsapp"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "channel_unavailable")
        self.assertEqual(MemorySender.outbox, [])

    def test_switching_channel_does_not_skip_the_cooldown(self):
        self.request_code()
        response = self.client.post(reverse("phone-request"), {"phone": "0612345678", "channel": "sms"})
        self.assertEqual(response.status_code, 429)

    def test_asking_again_too_soon_is_refused(self):
        self.request_code()
        response, _ = self.request_code()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "throttled")
        self.assertGreater(response.json()["retry_after"], 0)
        self.assertEqual(len(MemorySender.outbox), 1)

    def test_a_failed_send_is_reported_and_can_be_retried_at_once(self):
        with mock.patch.object(MemorySender, "send", side_effect=SendError):
            response, _ = self.request_code()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "send_failed")
        self.assertFalse(PhoneCode.objects.exists())
        response, _ = self.request_code()
        self.assertEqual(response.status_code, 202)

    @NO_COOLDOWN
    def test_requests_per_number_are_limited_whatever_the_address(self):
        with mock.patch.object(CodeRequestPhoneThrottle, "get_rate", return_value="2/hour"):
            statuses = [
                self.client.post(reverse("phone-request"), {"phone": "0612345678"}, REMOTE_ADDR=f"10.0.0.{i}").status_code
                for i in range(3)
            ]
        self.assertEqual(statuses, [202, 202, 429])


@CODES_ON
class VerifyCodeTests(ApiTestCase):
    def verify(self, code, phone="0612345678"):
        return self.client.post(reverse("phone-verify"), {"phone": phone, "code": code})

    def test_first_sign_in_creates_the_account(self):
        _, code = self.request_code()
        response = self.verify(code)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["is_new"])
        self.assertTrue(body["access"] and body["refresh"])
        self.assertEqual(body["user"]["phone"], "+212612345678")
        self.assertFalse(body["user"]["profile_complete"])
        user = User.objects.get()
        self.assertFalse(user.has_usable_password())  # code-only account: no password to guess

    @NO_COOLDOWN
    def test_signing_in_again_finds_the_same_account(self):
        _, code = self.request_code()
        first = self.verify(code).json()
        _, code = self.request_code("+212 612 345 678")
        second = self.verify(code).json()
        self.assertFalse(second["is_new"])
        self.assertEqual(first["user"]["id"], second["user"]["id"])
        self.assertEqual(User.objects.count(), 1)

    def test_a_code_works_once(self):
        _, code = self.request_code()
        self.assertEqual(self.verify(code).status_code, 200)
        response = self.verify(code)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "code_invalid")

    def test_wrong_codes_lock_the_code_after_five_tries(self):
        _, code = self.request_code()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.verify(wrong).json()["code"], "code_invalid")
        self.assertEqual(self.verify(code).status_code, 400)
        self.assertEqual(PhoneCode.objects.get().attempts, 5)

    def test_an_expired_code_is_refused(self):
        _, code = self.request_code()
        PhoneCode.objects.update(expires_at=timezone.now() - datetime.timedelta(seconds=1))
        self.assertEqual(self.verify(code).json()["code"], "code_invalid")

    @NO_COOLDOWN
    def test_a_new_code_retires_the_previous_one(self):
        _, first = self.request_code()
        _, second = self.request_code()
        if first != second:
            self.assertEqual(self.verify(first).status_code, 400)
        self.assertEqual(self.verify(second).status_code, 200)

    def test_a_code_for_one_number_does_not_work_for_another(self):
        _, code = self.request_code("0612345678")
        self.assertEqual(self.verify(code, phone="0612345679").status_code, 400)

    def test_a_disabled_account_cannot_sign_in(self):
        self.make_user(is_active=False)
        _, code = self.request_code()
        response = self.verify(code)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "account_disabled")

    def test_the_code_must_be_six_digits(self):
        self.request_code()
        self.assertEqual(self.verify("12ab56").status_code, 400)

    def test_guesses_per_number_are_limited_whatever_the_address(self):
        self.request_code()
        with mock.patch.object(CodeVerifyPhoneThrottle, "get_rate", return_value="3/hour"):
            statuses = [
                self.client.post(
                    reverse("phone-verify"), {"phone": "0612345678", "code": "123456"}, REMOTE_ADDR=f"10.0.1.{i}"
                ).status_code
                for i in range(4)
            ]
        self.assertEqual(statuses[-1], 429)
