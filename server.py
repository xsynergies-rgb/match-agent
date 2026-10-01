from http.server import SimpleHTTPRequestHandler, HTTPServer
import urllib.request

GOOGLE_SOURCE = "https://docs.google.com/document/d/1Uf8Zd6zfZyoXeNniPSCJhdl61xBEMS5k/export?format=txt"

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

        else:
            super().do_GET()


print("Match Agent running at http://localhost:8000")

HTTPServer(("0.0.0.0", 8000), MatchAgentServer).serve_forever()