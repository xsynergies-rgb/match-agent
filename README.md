# Glocal Sport — backend

The API behind the Glocal Sport app: players sign in with their phone, find a pickup football
match and ask for a spot; pitch owners confirm or decline and publish their slots.

Django 5.2 + Django REST Framework + SimpleJWT on Python 3.14, Postgres in production, deployed
on Render. Patterns follow the mekkapp backend (settings split, fail-closed production, thin views
over `services.py`, one error shape, per-address and per-identifier throttles, request ids).

The API contract the app relies on is in **[API.md](API.md)**.

## Layout

```
config/settings/   base.py (shared, safe defaults) · local.py · test.py · production.py · database.py
config/urls.py     /api/v1/… · /api/health/ · /api/ready/ · /admin/ — and a JSON 404 for anything else
common/            error envelope, request ids + log redaction, client address, throttles, health
apps/users/        phone sign-in (codes, senders, sessions), the User model, admin, sync_admins
apps/booking/      pitches, matches, reservations, owner actions, seed_pitches, assign_pitch_owner
```

## Run it locally

```bash
uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python -e .
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_pitches            # 9 pitches, 4–11 PM slots for 14 days
.venv/bin/python manage.py runserver 0.0.0.0:8000
```

Create an account from the app (phone + password). SQLite is used unless
`DATABASE_URL` is set.

To make someone a pitch owner (they must have signed in once):

```bash
.venv/bin/python manage.py assign_pitch_owner --phone 0612345678 --city Rabat --pitch Agdal
```

## Checks

```bash
DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py test
DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py makemigrations --check --dry-run
```

## How sign-in is protected

- Players sign up and sign in with their **phone number and a password** (at least 8 characters,
  not common, not all digits; hashed by Django). Numbers are normalised, so `0612345678` and
  `+212 6 12 34 56 78` are the same account; only Moroccan mobiles (`PHONE_ALLOWED_REGIONS`).
- Sign-in is throttled per IP *and* per phone number (20/min and 20/h), and every failure gets the
  same answer, so nobody can probe which numbers have accounts.
- Sessions: 15-minute access tokens, 30-day refresh tokens that rotate on every use. Logout,
  account deletion (needs the password) and the admin's "remove access" retire them. **Any password
  change** — in the app, in `/admin/`, or with `changepassword` — ends every session of that account.
- Forgotten password: the organizer sets a new one in `/admin/` (no SMS/email reset yet).
- Phone numbers aren't verified yet. Sign-in by one-time code (WhatsApp/SMS via Twilio) is built
  and tested, but off: set `PHONE_CODES_ENABLED=1` plus the Twilio settings to turn it on (codes are
  6 digits, 10 minutes, single use, 5 tries, stored as an HMAC, Moroccan mobiles only).
- Bookings need a signed-in player with a complete profile, are capped at 5 pending per player and
  30 requests an hour, and capacity is enforced under a row lock so a match can't be overfilled.
- Owners only see and act on their own pitches; anything else is a 404.

## Deploy on Render

`render.yaml` describes the service and its database. Before the first deploy:

1. **Twilio** — only if you turn on sign-in by code (`PHONE_CODES_ENABLED=1`): create an account, buy or verify a sender that can text Moroccan
   numbers, then set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_FROM` (a phone number,
   or a Messaging Service SID starting with `MG`). `OTP_CHANNELS=sms`.

   **WhatsApp codes** (optional, recommended in Morocco): in Twilio, register a WhatsApp sender (a
   business number linked to a Meta Business account, not used on a personal WhatsApp), create a
   template in the **Authentication** category (e.g. "{{1}} is your Glocal Sport code", copy-code
   button) and wait for Meta's approval. Then set `TWILIO_WHATSAPP_FROM` (the sender number),
   `TWILIO_WHATSAPP_CONTENT_SID` (the template's `HX…` id) and `OTP_CHANNELS=whatsapp,sms`: codes go
   by WhatsApp first and the app offers "Send by SMS instead" for numbers without WhatsApp.
2. Create the Blueprint from this repository. Production refuses to start if a required setting
   is missing, and never returns codes in responses.
3. Create your account in the app, put your phone in `GLOCAL_ADMIN_PHONES` and redeploy: you can then
   sign in to `/admin/` with the same phone and password. That's where bookings are confirmed,
   passwords are reset, pitches get owners and slots are managed.
4. Run `python manage.py seed_pitches` once from the Render shell to create the launch pitches,
   then give each pitch its **WhatsApp number** in `/admin/` → Pitches. Players who booked there
   message that number; a pitch without one falls back to the main organizer's number.

Render's free Postgres is deleted 30 days after creation, and the free web service sleeps when idle
(the first request after a pause takes a while). Use paid plans before real launch.
