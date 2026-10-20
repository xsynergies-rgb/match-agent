"""Delivering sign-in codes.

``OTP_SENDER`` picks how: ``console`` writes the code to the server log (development),
``twilio`` sends it by SMS or WhatsApp through Twilio's Messages API, ``memory`` keeps it in a
list for tests. Twilio is called over plain HTTPS, without its SDK.
"""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class SendError(Exception):
    pass


def message_text(code):
    minutes = int(settings.OTP_CODE_TTL.total_seconds() // 60)
    return f"Glocal Sport: your code is {code}. It expires in {minutes} minutes. Never share it."


class ConsoleSender:
    def send(self, phone, code, channel):
        logger.warning("Sign-in code for %s by %s: %s", phone, channel, code)


class MemorySender:
    outbox = []

    def send(self, phone, code, channel):
        self.outbox.append({"phone": phone, "code": code, "channel": channel})


class TwilioSender:
    def send(self, phone, code, channel):
        if channel == "whatsapp":
            # Business-started WhatsApp messages must use a pre-approved template; its {{1}} is the code.
            fields = {
                "To": f"whatsapp:{phone}",
                "From": f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}",
                "ContentSid": settings.TWILIO_WHATSAPP_CONTENT_SID,
                "ContentVariables": json.dumps({"1": code}),
            }
        else:
            sender_field = "MessagingServiceSid" if settings.TWILIO_FROM.startswith("MG") else "From"
            fields = {"To": phone, sender_field: settings.TWILIO_FROM, "Body": message_text(code)}

        credentials = f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()
        request = urllib.request.Request(
            TWILIO_MESSAGES_URL.format(sid=settings.TWILIO_ACCOUNT_SID),
            data=urllib.parse.urlencode(fields).encode(),
            headers={"Authorization": "Basic " + base64.b64encode(credentials).decode()},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
        except urllib.error.HTTPError as error:
            # Twilio's error body names the problem (bad number, unverified sender…) but never the code.
            detail = error.read().decode("utf-8", "replace")[:300]
            logger.error("Twilio refused a sign-in message (HTTP %s): %s", error.code, detail)
            raise SendError from error
        except (urllib.error.URLError, TimeoutError) as error:
            logger.error("Twilio could not be reached: %s", error)
            raise SendError from error


SENDERS = {"console": ConsoleSender, "memory": MemorySender, "twilio": TwilioSender}


def get_sender():
    return SENDERS[settings.OTP_SENDER]()
