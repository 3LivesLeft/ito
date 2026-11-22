# SPDX-License-Identifier: Apache-2.0
"""TEST-ONLY stand-in for the Supervisor's discovery endpoint. Records each discovery message to
/out/discovery.json.

    python3 -I fake_supervisor.py                 # TCP, on the internal test network ("supervisor")
    python3 -I fake_supervisor.py --unix PATH     # a root-owned 0600 socket, like the app socket of
                                                  # newer Supervisors (api/sockets.py)
"""

import json
import os
import socketserver
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        record = {"path": self.path, "auth": self.headers.get("Authorization"), "body": body}
        target = "discovery.json" if self.path == "/discovery" else "self-options.json"
        Path("/out", target).write_text(json.dumps(record))
        reply = json.dumps({"result": "ok", "data": {"uuid": "abc123"}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def address_string(self):
        return "client"

    def log_message(self, *args):
        pass


if len(sys.argv) == 3 and sys.argv[1] == "--unix":
    path = sys.argv[2]
    server = socketserver.ThreadingUnixStreamServer(path, Handler)
    os.chmod(path, 0o600)  # root-only, as the Supervisor makes it
    server.serve_forever()
else:
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()  # internal test network only
