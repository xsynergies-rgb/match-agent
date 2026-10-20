# Glocal Sport API — v1

Base URL: `{API_URL}/api/v1` (local: `http://localhost:8000/api/v1`).
All bodies are JSON. Times are local to Africa/Casablanca.

## Conventions

- **Auth:** `Authorization: Bearer <access>` on every endpoint not marked *public*.
- **Errors:** every non-2xx response has the same shape:

  ```json
  { "message": "Human readable, first problem", "code": "machine_code", "errors": { "field": ["…"] } }
  ```

  `429` responses also carry `"retry_after": <seconds>` and a `Retry-After` header.
- **Tokens:** access lives 15 minutes, refresh 30 days. Every refresh returns a *new*
  refresh token and retires the old one — always store the latest. A retired or
  logged-out refresh token gets `401`.
- Something that isn't yours (another player's booking, another owner's pitch) is `404`,
  never `403`.

## Shapes

```ts
type User = {
  id: string;                    // uuid
  phone: string;                 // E.164, e.g. "+212612345678"
  name: string;                  // "" until the profile is completed
  age_range: "" | "under_18" | "18_24" | "25_34" | "35_44" | "45_plus";
  gender: "" | "male" | "female";
  profile_complete: boolean;     // name, age_range and gender all set
  is_pitch_owner: boolean;       // owns at least one pitch (or is staff)
};

type Pitch = { id: number; city: string; name: string };

// Inside your own Reservation only: the pitch's WhatsApp number (E.164), null when it has none
// (the app then uses the main organizer's number). Public lists never include it.
type BookedPitch = Pitch & { phone: string | null };

type Match = {
  id: number;
  date: string;                  // "2026-10-20"
  start_time: string;            // "16:00"
  end_time: string;              // "17:00"
  capacity: number;
  spots_left: number;            // capacity minus confirmed bookings
  pitch: Pitch;
};

type OwnerMatch = Match & { is_open: boolean; confirmed_count: number; pending_count: number };

type Reservation = {
  id: string;                    // uuid
  status: "pending" | "confirmed" | "declined" | "cancelled";
  created_at: string;            // ISO 8601
  match: Match & { pitch: BookedPitch };
};

type OwnerReservation = Reservation & {
  player: { name: string; phone: string; age_range: User["age_range"]; gender: User["gender"] };
};
```

## Auth — phone number + password

| Method & path | Body | Success | Errors |
|---|---|---|---|
| `POST /auth/register/` *public* | `{ phone, password }` — phone in any common format (`"0612345678"`, `"+212 6 12 34 56 78"`); password at least 8 characters, not too common, not all digits | `201 { access, refresh, user: User, is_new: true }` — signed in straight away | `400` on `phone` (`invalid`, `region_not_allowed`, `not_mobile`, `phone_taken`) or `password` (too short/common/numeric), `429 throttled` |
| `POST /auth/login/` *public* | `{ phone, password }` | `200 { access, refresh, user: User, is_new: false }` | `401 invalid_credentials` — one answer for wrong password, unknown number and disabled account; `429 throttled` (per address, and per number whatever the address) |
| `POST /auth/password/change/` | `{ current_password, new_password }` | `200 { access, refresh }` — **store this new pair**: every other session (other phones, and this phone's old tokens) ends | `400 wrong_password` / weak `new_password`, `429` |
| `POST /auth/refresh/` *public* | `{ refresh }` | `200 { access, refresh }` | `401` |
| `POST /auth/logout/` | `{ refresh }` | `204` | `400` |
| `GET /auth/me/` | — | `200 User` | |
| `PATCH /auth/me/` | any of `{ name, age_range, gender }` | `200 User` | `400` |
| `DELETE /auth/me/` | `{ password }` | `204` — deletes the account and its bookings, signs out everywhere | `400 wrong_password` |

Forgotten password: there's no self-service reset yet (it needs SMS or email). The organizer sets a
new one in `/admin/` (Users → the player → "Reset password"), which also signs the player out everywhere.

### Sign-in by one-time code (off)

`POST /auth/phone/request/` and `POST /auth/phone/verify/` (code by WhatsApp or SMS) are built and
tested but answer `404` until the server sets `PHONE_CODES_ENABLED=1` with Twilio configured.
`request` takes `{ phone, channel? }` and returns `202 { phone, channel, channels, expires_in, resend_in }`;
`verify` takes `{ phone, code }` and returns the same body as `/auth/login/`.

## Public

| Method & path | Query | Success |
|---|---|---|
| `GET /pitches/` *public* | `city` (optional) | `200 Pitch[]` — active pitches, by city then name |
| `GET /matches/` *public* | `city`, `date` (YYYY-MM-DD), `pitch` (id, repeatable) — all optional | `200 Match[]` — only bookable matches: open, active pitch, not in the past, `spots_left > 0`. Without `date`: today to +14 days. Ordered by date, start time, city, pitch name. |

## Player

| Method & path | Body | Success | Errors |
|---|---|---|---|
| `POST /reservations/` | `{ match: number }` | `201 Reservation` (new) or `200 Reservation` (you already have an active booking for this match — same one returned) | `400 profile_incomplete`, `404` match, `409 match_unavailable` (closed, past or full), `409 too_many_pending` (max 5 pending at once) |
| `GET /reservations/` | — | `200 Reservation[]` — yours, newest first | |
| `GET /reservations/{id}/` | — | `200 Reservation` | `404` |
| `POST /reservations/{id}/cancel/` | — | `200 Reservation` | `409 not_cancellable` (already declined/cancelled, or the match has started) |

## Pitch owner

Needs `is_pitch_owner` (otherwise `403`). Everything is limited to the owner's own pitches.

| Method & path | Body / query | Success | Errors |
|---|---|---|---|
| `GET /owner/pitches/` | — | `200 Pitch[]` | |
| `GET /owner/reservations/` | `status` (optional, e.g. `pending`) | `200 OwnerReservation[]` — oldest first | |
| `POST /owner/reservations/{id}/confirm/` | — | `200 OwnerReservation` | `404`, `409 not_pending`, `409 match_full` |
| `POST /owner/reservations/{id}/decline/` | — | `200 OwnerReservation` | `404`, `409 not_pending` |
| `GET /owner/matches/` | `date`, `pitch` (optional) | `200 OwnerMatch[]` — includes closed and full ones | |
| `POST /owner/matches/` | `{ pitch, date, start_time, end_time, capacity }` | `201 OwnerMatch` | `400` (bad times, duplicate slot, past date), `404` pitch |
| `PATCH /owner/matches/{id}/` | any of `{ capacity, is_open }` | `200 OwnerMatch` | `400` (capacity below confirmed bookings), `404` |

## Service

- `GET /api/health/` → `200 {"status": "ok"}` (process is up)
- `GET /api/ready/` → `200 {"status": "ok"}` or `503` (database reachable) — Render's health check
- `GET /api/docs/` — interactive docs, local DEBUG server only
- `/admin/` — Django admin for staff
