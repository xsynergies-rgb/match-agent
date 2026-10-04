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

class MatchAgentServer(SimpleHTTPRequestHandler):

    def do_GET(self):

        if self.path == "/availability":

            try:
                with urllib.request.urlopen(GOOGLE_SOURCE) as response:
                    data = response.read()

                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(data)

            except Exception as error:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(error).encode())

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

        else:
            super().do_GET()


init_db()

print("Match Agent running at http://localhost:8000")

port = int(os.environ.get("PORT", 8000))
HTTPServer(("0.0.0.0", port), MatchAgentServer).serve_forever()
