from django.urls import reverse

from common.logging import redact
from common.testing import ApiTestCase


class ApiBasicsTests(ApiTestCase):
    def test_health_and_readiness(self):
        self.assertEqual(self.client.get(reverse("health")).json(), {"status": "ok"})
        self.assertEqual(self.client.get(reverse("ready")).json(), {"status": "ok"})

    def test_source_files_are_never_served(self):
        # The old server answered /server.py with its own source code.
        for path in ["/server.py", "/.git/HEAD", "/requirements.txt", "/manage.py", "/config/settings/base.py"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)
            self.assertEqual(response.json()["code"], "not_found")

    def test_errors_share_one_shape(self):
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertEqual(set(body), {"message", "code", "errors"})
        self.assertEqual(body["code"], "not_authenticated")

    def test_request_id_is_echoed_or_generated(self):
        response = self.client.get(reverse("health"), HTTP_X_REQUEST_ID="app-req-12345678")
        self.assertEqual(response["X-Request-ID"], "app-req-12345678")
        generated = self.client.get(reverse("health"), HTTP_X_REQUEST_ID="bad id!")["X-Request-ID"]
        self.assertRegex(generated, r"^[0-9a-f]{32}$")

    def test_logs_never_hold_tokens_or_full_phone_numbers(self):
        line = redact("Authorization: Bearer abc.def.ghi for +212612345678 token eyJa.eyJb.sig")
        self.assertNotIn("abc.def.ghi", line)
        self.assertNotIn("+212612345678", line)
        self.assertNotIn("eyJa.eyJb.sig", line)
