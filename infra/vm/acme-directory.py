"""Test-only directory redirect; all ACME operations go to the real Pebble server."""

import http.server
import ssl


class Directory(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/directory":
            self.send_error(404)
            return
        self.send_response(308)
        self.send_header("Location", "https://acme-v02.api.letsencrypt.org:14000/dir")
        self.send_header("Content-Length", "0")
        self.end_headers()


server = http.server.ThreadingHTTPServer(("0.0.0.0", 443), Directory)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("/config/server.pem", "/config/server.key")
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
