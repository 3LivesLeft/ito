# SPDX-License-Identifier: Apache-2.0
"""TEST-ONLY stand-in for the Supervisor's discovery endpoint, run in a container on the internal
test network with the alias "supervisor". Records each discovery message to /out/discovery.json.

    python3 -I fake_supervisor.py
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        record = {"path": self.path, "auth": self.headers.get("Authorization"), "body": body}
        Path("/out/discovery.json").write_text(json.dumps(record))
        reply = json.dumps({"result": "ok", "data": {"uuid": "abc123"}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()  # internal test network only
