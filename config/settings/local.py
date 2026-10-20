"""Development on your Mac: DEBUG on, SQLite unless DATABASE_URL is set, codes printed in the log."""

import os

os.environ.setdefault("SECRET_KEY", "local-development-only-not-a-secret")

from .base import *  # noqa: E402,F403

DEBUG = True
# The iOS simulator calls localhost, the Android emulator 10.0.2.2, a phone on Wi-Fi the Mac's LAN
# address; none of that matters with DEBUG on a laptop.
ALLOWED_HOSTS = ["*"]

# If phone codes are turned on (PHONE_CODES_ENABLED=1), the response includes the code, so they
# can be tried without a real phone.
OTP_DEBUG_RESPONSE = True
# Offer both channels so the app's "Send by SMS instead" can be tried; the console sender prints either.
OTP_CHANNELS = ["whatsapp", "sms"]
