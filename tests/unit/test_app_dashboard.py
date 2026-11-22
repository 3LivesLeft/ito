# SPDX-License-Identifier: Apache-2.0
"""Dashboard self-management, ingress boundary and upgrade regressions (no real Supervisor)."""

import copy
import http.client
import json
from pathlib import Path

import pytest

from meshbeacon.app_control import AppControl, perform, revision
from meshbeacon.ingress import Dashboard, IngressServer
from meshbeacon.recent_history import RecentHistory


class FakeSupervisor:
    def __init__(self):
        self.raw = {
            "network": "custom",
            "peers": [{"name": "Local", "host": "example.org", "port": 4242, "passphrase": "!secret peer_password"}],
            "messaging_enabled": True,
            "replace_identity": False,
        }
        self.writes = []

    def __call__(self, method, path, payload=None):
        assert path.startswith("/addons/self/")
        if method == "POST":
            self.writes.append((path, payload))
            if payload and "options" in payload:
                self.raw = payload["options"]
            return 200, {"result": "ok", "data": {}}
        if path.endswith("/info"):
            value = {"options": copy.deepcopy(self.raw)}
        else:
            value = copy.deepcopy(self.raw)
            for peer in value.get("peers", []):
                if peer.get("passphrase") == "!secret peer_password":
                    peer["passphrase"] = "test-only-passphrase"
        return 200, {"result": "ok", "data": value}


def test_settings_redact_secrets_and_retain_supervisor_references():
    supervisor = FakeSupervisor()
    visible = perform({"op": "config_read"}, supervisor)
    assert "test-only-passphrase" not in json.dumps(visible)
    assert "!secret" not in json.dumps(visible)
    assert "replace_identity" not in visible["options"]
    assert visible["options"]["peers"][0]["has_passphrase"]
    saved = perform(
        {"op": "config_save", "revision": visible["revision"], "patch": {"network": "ratspeak_ruby"}}, supervisor
    )
    assert saved["ok"]
    assert supervisor.raw["peers"][0]["passphrase"] == "!secret peer_password"
    assert supervisor.raw["messaging_enabled"] is True
    assert supervisor.raw["replace_identity"] is False


def test_peer_edit_can_keep_password_when_renaming_without_browser_receiving_it():
    supervisor = FakeSupervisor()
    answer = perform(
        {
            "op": "config_save",
            "revision": revision(supervisor.raw),
            "patch": {"peers": [{"name": "Renamed", "host": "example.net", "port": 4242, "keep_passphrase": "Local"}]},
        },
        supervisor,
    )
    assert answer["ok"]
    assert supervisor.raw["peers"][0]["passphrase"] == "!secret peer_password"


@pytest.mark.parametrize(
    "patch",
    [
        {"replace_identity": True},
        {"network": "invented"},
        {"peers": [{"host": "bad\nvalue"}]},
        {"messaging_enabled": "yes"},
        {"unknown": True},
    ],
)
def test_invalid_settings_never_write(patch):
    supervisor = FakeSupervisor()
    assert not perform({"op": "config_save", "revision": revision(supervisor.raw), "patch": patch}, supervisor)["ok"]
    assert supervisor.writes == []


def test_stale_form_cannot_overwrite_newer_configuration():
    supervisor = FakeSupervisor()
    result = perform({"op": "config_save", "revision": "old", "patch": {"network": "custom"}}, supervisor)
    assert result["error"] == "conflict"
    assert supervisor.writes == []


def test_only_fixed_self_management_operations():
    supervisor = FakeSupervisor()
    assert not perform({"op": "proxy", "path": "/core/restart"}, supervisor)["ok"]
    assert perform({"op": "sidebar_enable"}, supervisor)["ok"]
    assert perform({"op": "app_restart"}, supervisor)["ok"]
    assert supervisor.writes == [("/addons/self/options", {"ingress_panel": True}), ("/addons/self/restart", None)]


def test_relay_failure_never_falls_back_to_token():
    control = AppControl(None, "test-only-credential", socket_mode=True)
    assert control.token is None
    assert control.request({"op": "config_read"}) == {"ok": False, "error": "unavailable"}


class FakeControl:
    def __init__(self):
        self.operations = []

    def request(self, request):
        self.operations.append(request)
        return {"ok": True, "options": {}, "revision": "test"}


@pytest.fixture
def dashboard(tmp_path):
    (tmp_path / "ingress.js").write_text("// app")
    control = FakeControl()
    return Dashboard(control, lambda request: (200, {"ok": True, "op": request["op"]}), tmp_path)


def request(server, path, body=None, headers=None):
    client = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    client.request(
        "GET" if body is None else "POST", path, body, {"X-Remote-User-Groups": "system-admin", **(headers or {})}
    )
    response = client.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    client.close()
    return result


def test_ingress_refuses_spoofed_forwarded_peer(dashboard):
    server = IngressServer(dashboard, "127.0.0.1", 0)
    server.start()
    try:
        assert request(server, "/", headers={"X-Forwarded-For": "172.30.32.2"})[0] == 403
    finally:
        server.stop()


def test_ingress_cache_paths_csrf_and_messaging(dashboard):
    server = IngressServer(dashboard, "127.0.0.1", 0, allowed_peer="127.0.0.1")
    server.start()
    try:
        assert request(server, "/", headers={"X-Remote-User-Groups": "system-users"})[0] == 403
        assert request(server, "/", headers={"X-Remote-User-Groups": ""})[0] == 403
        status, headers, html = request(server, "/", headers={"X-Ingress-Path": "/api/hassio_ingress/test-session"})
        assert status == 200 and headers["Cache-Control"] == "no-store"
        assert f"/api/hassio_ingress/test-session/assets/{dashboard.build}/ingress.js".encode() in html
        status, headers, content = request(server, f"/assets/{dashboard.build}/ingress.js")
        assert status == 200 and "immutable" in headers["Cache-Control"] and content == b"// app"
        assert request(server, "/assets/stale/ingress.js")[0] == 404
        assert request(server, f"/assets/{dashboard.build}//etc/test.js")[0] == 404
        assert request(server, f"/assets/{dashboard.build}/../ingress.js")[0] == 404
        assert request(server, "/api/messaging", '{"op":"conversations"}')[0] == 403
        headers = {"Content-Type": "application/json", "X-Ito-Request": "1"}
        status, _, body = request(server, "/api/messaging", '{"op":"conversations"}', headers)
        assert status == 200 and json.loads(body)["op"] == "conversations"
        assert request(server, "/api/config", "{" * 32769, headers)[0] == 400
        assert request(server, "/api/config", '{"op":"delete_identity"}', headers)[0] == 400
    finally:
        server.stop()


def test_sidebar_once_respects_later_user_choice(dashboard, tmp_path):
    marker = tmp_path / "sidebar.json"
    dashboard.add_sidebar(marker)
    dashboard.add_sidebar(marker)
    assert dashboard.control.operations == [{"op": "sidebar_enable"}]
    assert marker.exists()


def test_frontend_content_changes_invalidate_every_relative_asset(tmp_path):
    path = tmp_path / "brand-mark.js"
    path.write_text("old")
    first = Dashboard(FakeControl(), lambda _: (200, {}), tmp_path).build
    path.write_text("new")
    assert Dashboard(FakeControl(), lambda _: (200, {}), tmp_path).build != first


def test_recent_history_is_bounded_and_unknown_is_not_zero():
    history = RecentHistory()
    for stamp in range(0, 8 * 86400, 60):
        history.add({"network": {"rx_rate": 2000}, "resources": {}}, stamp)
    assert len(history.short) == 288 and len(history.long) == 168
    assert history.read(False)["receive_rate"][-1]["v"] == 2
    assert history.read(True)["memory"][-1]["v"] is None


def test_app_bundle_matches_shared_frontend():
    root = Path(__file__).resolve().parents[2]
    source = root / "custom_components/meshbeacon/frontend"
    target = root / "meshbeacon/frontend"
    assert {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()} == {
        p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()
    }


def test_pages_endpoint_is_csrf_protected_and_off_unless_switched_on(tmp_path):
    """v0.6 (ADR 0027): /api/pages follows the same Ingress rules; without pages it is refused."""
    (tmp_path / "ingress.js").write_text("// app")
    seen = []
    off = Dashboard(FakeControl(), lambda request: (200, {"ok": True}), tmp_path)
    on = Dashboard(
        FakeControl(),
        lambda request: (200, {"ok": True}),
        tmp_path,
        pages=lambda r: (seen.append(r), (200, {"ok": True}))[1],
    )
    headers = {"Content-Type": "application/json", "X-Ito-Request": "1"}
    for dashboard, expected in ((off, 409), (on, 200)):
        server = IngressServer(dashboard, "127.0.0.1", 0, allowed_peer="127.0.0.1")
        server.start()
        try:
            assert request(server, "/api/pages", '{"op":"overview"}')[0] == 403  # no CSRF header
            assert (
                request(server, "/api/pages", '{"op":"overview"}', {**headers, "X-Remote-User-Groups": "users"})[0]
                == 403
            )
            assert request(server, "/api/pages", "{" * 65537, headers)[0] == 400
            status, _, body = request(server, "/api/pages", '{"op":"overview"}', headers)
            assert status == expected, body
        finally:
            server.stop()
    assert seen == [{"op": "overview"}]


def test_a_full_page_of_escaped_text_fits_the_pages_body_limit(tmp_path):
    """32 KiB of backslashes is 64 KiB once JSON-escaped: still accepted on /api/pages only."""
    (tmp_path / "ingress.js").write_text("// app")
    dashboard = Dashboard(FakeControl(), lambda r: (200, {"ok": True}), tmp_path, pages=lambda r: (200, {"ok": True}))
    server = IngressServer(dashboard, "127.0.0.1", 0, allowed_peer="127.0.0.1")
    server.start()
    try:
        headers = {"Content-Type": "application/json", "X-Ito-Request": "1"}
        body = json.dumps({"op": "page_save", "title": "x", "content": "\\" * 32768})
        assert request(server, "/api/pages", body, headers)[0] == 200
        assert request(server, "/api/messaging", body, headers)[0] == 400  # unchanged elsewhere
    finally:
        server.stop()
