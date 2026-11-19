# SPDX-License-Identifier: Apache-2.0
"""Smoke test of the MeshBeacon integration in a real Home Assistant (no test harness).

Starts a fake MeshBeacon status API on 127.0.0.1 and a real Home Assistant with the integration
and a pre-configured entry. It lets Home Assistant poll for a while, stops it, and checks
Home Assistant's own recorder database and log. Used in CI with the Home Assistant release that the
reference installation runs (the pytest harness lags new releases).

    python tools/ha_smoke_test.py --hass-python /path/to/venv/bin/python [--seconds 200]

Nothing here leaves the machine: the API and Home Assistant listen on 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "meshbeacon" / "core"))
from meshbeacon.tlscert import generate  # noqa: E402 - after the path is set
from tests.ha.fixtures import snapshot  # noqa: E402

TOKEN = "S" * 43
STRAY = "M" * 43  # stands in for any credential that must not be stored in Home Assistant
ENTRY_KEYS = {"host", "port", "token", "cert_sha256", "node_key", "app_slug"}
HASS_URL = "http://127.0.0.1:8123"  # Home Assistant's default port, bound to loopback below
EXPECTED_ENABLED = 23  # entities enabled by default, with one peer (keep in step with sensor.py)


def serve_api(port: int, calls: list[bool], certs: Path) -> tuple[HTTPServer, str]:
    """The same HTTPS set-up as the app: a throwaway certificate, pinned by its fingerprint."""
    fingerprint = generate(certs)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            ok = self.path == "/api/v1/status" and self.headers.get("Authorization") == f"Bearer {TOKEN}"
            calls.append(ok)
            body = json.dumps(snapshot()).encode() if ok else b'{"error":"unauthorised"}'
            self.send_response(200 if ok else 401)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(certs / "cert.pem", certs / "key.pem")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, fingerprint


def write_config(config: Path, port: int, fingerprint: str) -> None:
    (config / ".storage").mkdir(parents=True)
    shutil.copytree(ROOT / "custom_components" / "meshbeacon", config / "custom_components" / "meshbeacon")
    (config / "configuration.yaml").write_text(
        "homeassistant:\n  name: MeshBeacon smoke test\n  time_zone: Europe/London\n  country: GB\n"
        "  unit_system: metric\n"
        f"http:\n  server_host: 127.0.0.1\n"
        f"recorder:\n  db_url: sqlite:///{config}/home-assistant_v2.db\n  commit_interval: 1\n"
        "logger:\n  default: warning\n  logs:\n    custom_components.meshbeacon: debug\n"
    )
    entry = {
        "entry_id": "01SMOKETEST000000000000000",
        "version": 1,
        "domain": "meshbeacon",
        "title": "MeshBeacon",
        # A v0.2 entry (version 1), plus a field that must never be kept (M1: only ENTRY_KEYS).
        "data": {"host": "127.0.0.1", "port": port, "token": TOKEN, "cert_sha256": fingerprint, "stray": STRAY},
        "options": {},
        "pref_disable_new_entities": False,
        "pref_disable_polling": False,
        "source": "hassio",
        "unique_id": "local_meshbeacon",
        "disabled_by": None,
    }
    storage = {"version": 1, "minor_version": 1, "key": "core.config_entries", "data": {"entries": [entry]}}
    (config / ".storage" / "core.config_entries").write_text(json.dumps(storage))


def check_panel() -> list[str]:
    """The sidebar panel's route and module, as an unauthenticated browser sees them (ADR 0007)."""
    found: list[str] = []
    try:
        with urllib.request.urlopen(f"{HASS_URL}/meshbeacon", timeout=10) as page:  # noqa: S310 - loopback
            if page.status != 200:
                found.append(f"panel route /meshbeacon returned {page.status}")
        with urllib.request.urlopen(f"{HASS_URL}/meshbeacon_panel/meshbeacon-panel.js", timeout=10) as js:  # noqa: S310
            body = js.read().decode()
            if "customElements.define" not in body or TOKEN in body:
                found.append("panel module missing or wrong")
    except (urllib.error.URLError, OSError) as exc:
        found.append(f"panel not served: {exc}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hass-python", required=True)
    parser.add_argument("--seconds", type=int, default=200)
    parser.add_argument("--port", type=int, default=18100)
    args = parser.parse_args()
    calls: list[bool] = []
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "certs").mkdir(mode=0o700)
        server, fingerprint = serve_api(args.port, calls, Path(tmp) / "certs")
        config = Path(tmp) / "config"
        write_config(config, args.port, fingerprint)
        version = subprocess.run(
            [args.hass_python, "-c", "import homeassistant.const as c; print(c.__version__)"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        output = Path(tmp) / "hass.out"
        with output.open("wb") as out:
            proc = subprocess.Popen(
                [args.hass_python, "-m", "homeassistant", "-c", str(config), "--skip-pip"],
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        deadline = time.monotonic() + args.seconds
        panel_problems: list[str] | None = None
        while time.monotonic() < deadline and proc.poll() is None:
            time.sleep(1)
            if panel_problems is None and time.monotonic() > deadline - args.seconds / 2:
                panel_problems = check_panel()
        exited_early = proc.poll() is not None
        proc.terminate()
        try:
            proc.wait(60)
        except subprocess.TimeoutExpired:
            proc.kill()
        server.shutdown()
        log = "\n".join(p.read_text() for p in sorted(config.glob("home-assistant.log*")))
        try:
            db = sqlite3.connect(config / "home-assistant_v2.db")
            rows = db.execute(
                "select m.entity_id, s.state from states s join states_meta m on s.metadata_id = m.metadata_id "
                "where m.entity_id like '%meshbeacon%' group by m.entity_id"
            ).fetchall()
            db.close()
        except sqlite3.Error as exc:
            rows = []
            print(f"recorder database unusable: {exc}")
        states = dict(rows)
        registry = config / ".storage" / "core.entity_registry"
        entities = json.loads(registry.read_text())["data"]["entities"] if registry.exists() else []
        ours = [e for e in entities if e["platform"] == "meshbeacon"]
        stored = json.loads((config / ".storage" / "core.config_entries").read_text())["data"]["entries"]
        storage_text = "\n".join(p.read_text(errors="replace") for p in (config / ".storage").iterdir() if p.is_file())
        hass_output = output.read_text(errors="replace")
    problems = ["panel not checked (Home Assistant stopped too early)"] if panel_problems is None else panel_problems
    if exited_early:
        problems.append(f"Home Assistant exited early (code {proc.returncode})")
    polls = sum(calls)
    if polls < max(2, args.seconds // 60 - 1):
        problems.append(f"only {polls} successful polls in {args.seconds} s")
    if not all(calls):
        problems.append("a request was refused (wrong key)")
    if len(states) != EXPECTED_ENABLED:
        problems.append(f"{len(states)} entities recorded, expected {EXPECTED_ENABLED}")
    expected = {
        "sensor.meshbeacon_status": "running",
        "sensor.meshbeacon_connectivity": "online",
        "sensor.meshbeacon_known_paths": "42",
        "sensor.meshbeacon_links_relayed_for_others": "2",
        "binary_sensor.meshbeacon_emerald_connected": "on",
    }
    for entity_id, value in expected.items():
        if states.get(entity_id) != value:
            problems.append(f"{entity_id} = {states.get(entity_id)!r}, expected {value!r}")
    # Config entry migration v1 → v2 on this release (M1): the node key is the old unique ID, so no
    # entity changes; only the allowed keys are kept.
    entry = stored[0] if stored else {}
    if entry.get("version") != 2:
        problems.append(f"config entry version {entry.get('version')}, expected 2 after migration")
    data = entry.get("data", {})
    if data.get("node_key") != "local_meshbeacon" or data.get("app_slug") != "local_meshbeacon":
        problems.append("config entry migration did not set node_key and app_slug")
    if not set(data) <= ENTRY_KEYS or STRAY in storage_text:
        problems.append("a field outside the allowed entry keys was kept in Home Assistant's storage")
    if not ours or not all(e["unique_id"].startswith("local_meshbeacon_") for e in ours):
        problems.append("entity unique IDs do not use the node key")
    bad = [line for line in log.splitlines() if "meshbeacon" in line and (" ERROR " in line or "Traceback" in line)]
    problems += [f"log: {line[:200]}" for line in bad]
    if TOKEN in log or STRAY in log:
        problems.append("a key appears in Home Assistant's log")
    print(
        f"Home Assistant {version}: {polls} polls, {len(ours)} entities registered "
        f"({sum(1 for e in ours if e.get('disabled_by'))} disabled by default), {len(states)} recorded, "
        f"panel {'served' if panel_problems == [] else 'NOT served'}"
    )
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:  # enough context to diagnose a failure in CI
        print("--- Home Assistant output (last 60 lines) ---")
        print("\n".join(hass_output.splitlines()[-60:]))
        print("--- Home Assistant log: errors and warnings ---")
        print("\n".join(line[:300] for line in log.splitlines() if " ERROR " in line or " WARNING " in line))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
