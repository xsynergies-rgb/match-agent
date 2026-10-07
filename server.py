from http.server import SimpleHTTPRequestHandler, HTTPServer
import urllib.request
import os
import json
import psycopg

GOOGLE_SOURCE = "https://docs.google.com/document/d/1Uf8Zd6zfZyoXeNniPSCJhdl61xBEMS5k/export?format=txt"
PITCH_OWNER_TOKEN = os.environ.get("PITCH_OWNER_TOKEN")

def init_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pitch_owners (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        phone TEXT UNIQUE NOT NULL,
                        auth_token TEXT UNIQUE NOT NULL,
                        status TEXT NOT NULL DEFAULT 'Active'
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pitches (
                        id SERIAL PRIMARY KEY,
                        city TEXT NOT NULL,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'Active',
                        owner_id INTEGER REFERENCES pitch_owners(id),
                        UNIQUE(city, name)
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS matches (
                        id SERIAL PRIMARY KEY,
                        pitch_id INTEGER NOT NULL REFERENCES pitches(id),
                        date DATE NOT NULL,
                        time TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'Available',
                        capacity INTEGER NOT NULL DEFAULT 10,
                        spots_left INTEGER NOT NULL DEFAULT 10,
                        UNIQUE(pitch_id, date, time),
                        CHECK(capacity > 0),
                        CHECK(spots_left >= 0),
                        CHECK(spots_left <= capacity)
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS reservations (
                        id SERIAL PRIMARY KEY,
                        match_id INTEGER NOT NULL REFERENCES matches(id),
                        player_name TEXT NULL,
                        player_phone TEXT NULL,
                        status TEXT NOT NULL DEFAULT 'Pending',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    ALTER TABLE reservations
                    ADD COLUMN IF NOT EXISTS request_id TEXT;
                """)
                cur.execute("""
                    ALTER TABLE reservations
                    ADD COLUMN IF NOT EXISTS player_age_range TEXT;
                """)

                cur.execute("""
                    ALTER TABLE reservations
                    ADD COLUMN IF NOT EXISTS player_gender TEXT;
                """)

                cur.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS reservations_request_id_unique
                    ON reservations (request_id)
                    WHERE request_id IS NOT NULL;
                """)
                if PITCH_OWNER_TOKEN:
                    cur.execute("""
                        INSERT INTO pitch_owners (name, phone, auth_token)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (phone) DO UPDATE
                        SET auth_token = EXCLUDED.auth_token,
                            status = 'Active'
                        RETURNING id;
                    """, ("Agdal Pitch Owner", "TEST-AGDAL-OWNER", PITCH_OWNER_TOKEN))

                    owner_id = cur.fetchone()[0]

                    cur.execute("""
                        UPDATE pitches
                        SET owner_id = %s
                        WHERE id = 1;
                    """, (owner_id,))
            conn.commit()
    except Exception:
        print("Database initialization failed safely.")

def seed_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return

    pitches_data = [
        ("Rabat", "Agdal"),
        ("Rabat", "Hay Riad"),
        ("Rabat", "Hay El Fath"),
        ("Casablanca", "Maarif"),
        ("Casablanca", "Oulfa"),
        ("Casablanca", "Bernoussi"),
        ("Marrakesh", "Gueliz"),
        ("Marrakesh", "Mhamid"),
        ("Marrakesh", "Targa"),
    ]

    time_slots = [
        "4-5 PM",
        "5-6 PM",
        "6-7 PM",
        "7-8 PM",
        "8-9 PM",
        "9-10 PM",
        "10-11 PM",
    ]

    match_date = "2026-10-04"

    specific_spots = {
        ("Rabat", "Agdal"): 2,
        ("Rabat", "Hay Riad"): 5,
        ("Rabat", "Hay El Fath"): 7,
        ("Casablanca", "Maarif"): 1,
        ("Casablanca", "Oulfa"): 4,
        ("Casablanca", "Bernoussi"): 6,
        ("Marrakesh", "Gueliz"): 3,
        ("Marrakesh", "Mhamid"): 8,
        ("Marrakesh", "Targa"): 9,
    }

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                for city, name in pitches_data:
                    cur.execute("""
                        INSERT INTO pitches (city, name, status, owner_id)
                        VALUES (%s, %s, 'Active', NULL)
                        ON CONFLICT (city, name) DO NOTHING;
                    """, (city, name))

                conn.commit()

                for city, name in pitches_data:
                    cur.execute("""
                        SELECT id FROM pitches WHERE city = %s AND name = %s;
                    """, (city, name))
                    row = cur.fetchone()
                    if not row:
                        continue
                    pitch_id = row[0]

                    for slot in time_slots:
                        spots = 10
                        if slot == "6-7 PM" and (city, name) in specific_spots:
                            spots = specific_spots[(city, name)]

                        cur.execute("""
                            INSERT INTO matches (pitch_id, date, time, status, capacity, spots_left)
                            VALUES (%s, %s, %s, 'Available', 10, %s)
                            ON CONFLICT (pitch_id, date, time) DO NOTHING;
                        """, (pitch_id, match_date, slot, spots))

                conn.commit()
    except Exception:
        print("Database seeding failed safely.")

class MatchAgentServer(SimpleHTTPRequestHandler):

    def do_GET(self):

        if self.path == "/availability":
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"AVAILABILITY UNAVAILABLE")
                return

            try:
                with psycopg.connect(database_url) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT matches.id, pitches.city, matches.date, pitches.name, matches.time, matches.status, matches.spots_left
                            FROM matches
                            JOIN pitches ON matches.pitch_id = pitches.id
                            WHERE pitches.status = 'Active'
                              AND matches.status = 'Available'
                              AND matches.spots_left > 0
                            ORDER BY matches.date ASC,
                                     pitches.city ASC,
                                     pitches.name ASC,
                                     matches.id ASC;
                        """)
                        rows = cur.fetchall()

                lines = []
                for row in rows:
                    match_id, city, date_val, pitch_name, match_time, status, spots_left = row
                    date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)
                    lines.extend([
                        str(match_id),
                        str(city),
                        date_str,
                        str(pitch_name),
                        str(match_time),
                        str(status),
                        str(spots_left)
                    ])

                output_text = "\n".join(lines)
                if output_text:
                    output_text += "\n"

                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(output_text.encode("utf-8"))

            except Exception:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"AVAILABILITY UNAVAILABLE")

        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/reserve":
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"RESERVATION_FAILED"}')
                return

            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode('utf-8'))
            except Exception:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"INVALID_REQUEST"}')
                return

            if not isinstance(data, dict):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"INVALID_REQUEST"}')
                return

            match_id = data.get("match_id")
            if not isinstance(match_id, int):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"INVALID_REQUEST"}')
                return

            request_id = data.get("request_id")
            if not isinstance(request_id, str) or not request_id.strip():
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"INVALID_REQUEST"}')
                return

            player_name = data.get("player_name")
            if player_name is not None and not isinstance(player_name, str):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"INVALID_REQUEST"}')
                return

            player_phone = data.get("player_phone")
            if player_phone is not None and not isinstance(player_phone, str):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"INVALID_REQUEST"}')
                return
            player_age_range = data.get("player_age_range")
            if player_age_range not in ["Under 18", "18-24", "25-34", "35-44", "45+"]:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"INVALID_AGE_RANGE"}')
                return

            player_gender = data.get("player_gender")
            if player_gender not in ["Male", "Female"]:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"INVALID_GENDER"}')
                return

            conn = None
            try:
                conn = psycopg.connect(database_url)
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT r.id, r.match_id, m.spots_left
                            FROM reservations r
                            JOIN matches m ON m.id = r.match_id
                            WHERE r.request_id = %s;
                        """, (request_id,))

                        existing_request = cur.fetchone()

                        if existing_request:
                            if existing_request[1] != match_id:
                                raise ValueError("REQUEST_ID_MATCH_CONFLICT")

                            reservation_id = existing_request[0]
                            spots_left = existing_request[2]
                        else:
                            cur.execute("""
                                SELECT id, spots_left
                                FROM matches
                                WHERE id = %s
                                  AND status = 'Available'
                                  AND spots_left > 0;
                            """, (match_id,))
                            row = cur.fetchone()

                            if not row:
                                raise ValueError("MATCH_UNAVAILABLE")

                            updated_match_id, spots_left = row[0], row[1]

                            cur.execute("""
                                INSERT INTO reservations (
                                    match_id,
                                    player_name,
                                    player_phone,
                                    player_age_range,
                                    player_gender,
                                    status,
                                    request_id
                                )
                                VALUES (%s, %s, %s, %s, %s, 'Pending', %s)
                                ON CONFLICT (request_id)
                                WHERE request_id IS NOT NULL
                                DO NOTHING
                                RETURNING id;
                            """, (
                                match_id,
                                player_name,
                                player_phone,
                                player_age_range,
                                player_gender,
                                request_id
                            ))

                            res_row = cur.fetchone()

                            if res_row:
                                reservation_id = res_row[0]
                            else:
                                cur.execute("""
                                    SELECT id, match_id
                                    FROM reservations
                                    WHERE request_id = %s;
                                """, (request_id,))

                                existing_reservation = cur.fetchone()

                                if existing_reservation[1] != match_id:
                                    raise ValueError("REQUEST_ID_MATCH_CONFLICT")

                                reservation_id = existing_reservation[0]

                response_data = {
                    "success": True,
                    "reservation_id": reservation_id,
                    "match_id": match_id,
                    "spots_left": spots_left
                }
                response_bytes = json.dumps(response_data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(response_bytes)

            except Exception as e:
                if str(e) == "MATCH_UNAVAILABLE":
                    self.send_response(409)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b'{"success":false,"error":"MATCH_UNAVAILABLE"}')
                else:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b'{"success":false,"error":"RESERVATION_FAILED"}')
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

        elif self.path == "/confirm-reservation":
            provided_token = self.headers.get("X-Pitch-Owner-Token")
            admin_token = os.environ.get("GLOCAL_SPORT_ADMIN_TOKEN")

            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"CONFIRMATION_FAILED"}')
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode("utf-8"))

                reservation_id = data.get("reservation_id")

                if not isinstance(reservation_id, int):
                    raise ValueError("INVALID_REQUEST")

                with psycopg.connect(database_url) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                                SELECT r.match_id
                               FROM reservations r
                               JOIN matches m ON m.id = r.match_id
                               JOIN pitches p ON p.id = m.pitch_id
                               LEFT JOIN pitch_owners po ON po.id = p.owner_id
                               WHERE r.id = %s
                                 AND r.status = 'Pending'
                                 AND (
                                   (po.auth_token = %s AND po.status = 'Active')
          OR (%s::text IS NOT NULL AND %s::text = %s::text)
      )
    FOR UPDATE OF r;
""", (
    reservation_id,
    provided_token,
    admin_token,
    provided_token,
    admin_token
))

                        reservation = cur.fetchone()

                        if not reservation:
                            raise ValueError("UNAUTHORIZED_OR_NOT_PENDING")

                        match_id = reservation[0]
                        cur.execute("""
                            UPDATE matches
                            SET
                                spots_left = spots_left - 1,
                                status = CASE
                                    WHEN spots_left - 1 = 0 THEN 'Not Available'
                                    ELSE status
                                END
                            WHERE id = %s
                              AND status = 'Available'
                              AND spots_left > 0
                            RETURNING spots_left;
                        """, (match_id,))

                        match = cur.fetchone()

                        if not match:
                            raise ValueError("MATCH_UNAVAILABLE")

                        spots_left = match[0]

                        cur.execute("""
                            UPDATE reservations
                            SET status = 'Confirmed'
                            WHERE id = %s;
                        """, (reservation_id,))

                response_data = {
                    "success": True,
                    "reservation_id": reservation_id,
                    "status": "Confirmed",
                    "spots_left": spots_left
                }

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode("utf-8"))

            except ValueError as e:
                error = str(e)

                if error == "INVALID_REQUEST":
                    status_code = 400
                elif error == "RESERVATION_NOT_PENDING":
                    status_code = 409
                elif error == "MATCH_UNAVAILABLE":
                    status_code = 409
                else:
                    status_code = 500

                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"success": False, "error": error}).encode("utf-8")
                )

            except Exception as e:
                print("CONFIRMATION ERROR:", repr(e), flush=True)
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"CONFIRMATION_FAILED"}')

        elif self.path == "/decline-reservation":
            provided_token = self.headers.get("X-Pitch-Owner-Token")
            admin_token = os.environ.get("GLOCAL_SPORT_ADMIN_TOKEN")
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"DECLINE_FAILED"}')
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode("utf-8"))

                reservation_id = data.get("reservation_id")

                if not isinstance(reservation_id, int):
                    raise ValueError("INVALID_REQUEST")

                with psycopg.connect(database_url) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE reservations r
                            SET status = 'Declined'
                            FROM matches m, pitches p
                            LEFT JOIN pitch_owners po ON po.id = p.owner_id
                            WHERE r.id = %s
                              AND r.status = 'Pending'
                              AND m.id = r.match_id
                              AND p.id = m.pitch_id
                              AND (
                                  (po.auth_token = %s AND po.status = 'Active')
                                  OR (%s::text IS NOT NULL AND %s::text = %s::text)
                              )
                            RETURNING r.id, r.match_id;
                        """, (
                            reservation_id,
                            provided_token,
                            admin_token,
                            provided_token,
                            admin_token
                        ))
                        reservation = cur.fetchone()

                        if not reservation:
                            raise ValueError("UNAUTHORIZED_OR_NOT_PENDING")

                response_data = {
                    "success": True,
                    "reservation_id": reservation_id,
                    "status": "Declined"
                }

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode("utf-8"))

            except ValueError as e:
                error = str(e)

                if error == "INVALID_REQUEST":
                    status_code = 400
                elif error == "UNAUTHORIZED_OR_NOT_PENDING":
                    status_code = 403
                else:
                    status_code = 500

                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"success": False, "error": error}).encode("utf-8")
                )

            except Exception:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"error":"DECLINE_FAILED"}')

        else:
            self.send_response(404)
            self.end_headers()


init_db()
seed_db()

print("Match Agent running at http://localhost:8000")

port = int(os.environ.get("PORT", 8000))
HTTPServer(("0.0.0.0", port), MatchAgentServer).serve_forever()
