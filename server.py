from http.server import SimpleHTTPRequestHandler, HTTPServer
import urllib.request
import os
import psycopg

GOOGLE_SOURCE = "https://docs.google.com/document/d/1Uf8Zd6zfZyoXeNniPSCJhdl61xBEMS5k/export?format=txt"

def init_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pitches (
                        id SERIAL PRIMARY KEY,
                        city TEXT NOT NULL,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'Active',
                        owner_id INTEGER NULL,
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
                        status TEXT NOT NULL DEFAULT 'Confirmed',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)
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
                            SELECT pitches.city, matches.date, pitches.name, matches.time, matches.status, matches.spots_left
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
                    city, date_val, pitch_name, match_time, status, spots_left = row
                    date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)
                    lines.extend([
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

        elif self.path == "/db-test":
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"DATABASE_URL missing")
                return

            try:
                with psycopg.connect(database_url) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1;")
                        result = cur.fetchone()

                if result and result[0] == 1:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"DATABASE CONNECTION OK")
                else:
                    self.send_response(500)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"DATABASE CONNECTION FAILED")

            except Exception:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"DATABASE CONNECTION FAILED")

        elif self.path == "/db-tables":
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"DATABASE TABLES MISSING")
                return

            try:
                with psycopg.connect(database_url) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT table_name 
                            FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                              AND table_name = ANY(%s);
                        """, (['pitches', 'matches', 'reservations'],))
                        rows = cur.fetchall()
                        found_tables = {row[0] for row in rows}

                if {'pitches', 'matches', 'reservations'}.issubset(found_tables):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"DATABASE TABLES OK")
                else:
                    self.send_response(500)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"DATABASE TABLES MISSING")

            except Exception:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"DATABASE TABLE CHECK FAILED")

        elif self.path == "/db-seed-check":
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"SEED DATA CHECK FAILED")
                return

            try:
                with psycopg.connect(database_url) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM pitches;")
                        p_count = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM matches;")
                        m_count = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM reservations;")
                        r_count = cur.fetchone()[0]

                if p_count == 9 and m_count == 63 and r_count == 0:
                    response_text = f"PITCHES: {p_count}\nMATCHES: {m_count}\nRESERVATIONS: {r_count}\nSEED DATA OK"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(response_text.encode("utf-8"))
                else:
                    response_text = f"PITCHES: {p_count}\nMATCHES: {m_count}\nRESERVATIONS: {r_count}\nSEED DATA MISMATCH"
                    self.send_response(500)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(response_text.encode("utf-8"))

            except Exception:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"SEED DATA CHECK FAILED")

        else:
            super().do_GET()


init_db()
seed_db()

print("Match Agent running at http://localhost:8000")

port = int(os.environ.get("PORT", 8000))
HTTPServer(("0.0.0.0", port), MatchAgentServer).serve_forever()
