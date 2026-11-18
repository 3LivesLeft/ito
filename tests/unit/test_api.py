# SPDX-License-Identifier: Apache-2.0
"""Local monitoring API and Supervisor discovery (ADR 0006)."""

import http.client
import io
import json
import socket
import threading
import time
import urllib.error

import pytest

from meshbeacon.api import API_PATH, ApiServer, Discovery, StatusStore, new_token


@pytest.fixture
def server():
    token = new_token()
    store = StatusStore(token)
    srv = ApiServer(store, "127.0.0.1", 0, max_concurrent=2)
    srv.start()
    yield srv, store, token
    srv.stop()


def get(port, path=API_PATH, headers=None, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), body


def test_token_is_long_and_random():
    tokens = {new_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(t) >= 43 for t in tokens)  # 256 bits, URL-safe base64


def test_requires_bearer_token(server):
    srv, store, token = server
    store.publish({"schema": 1})
    assert get(srv.port)[0] == 401
    status, headers, _ = get(srv.port, headers={"Authorization": "Bearer wrong"})
    assert status == 401 and headers["WWW-Authenticate"] == "Bearer"
    assert get(srv.port, headers={"Authorization": f"Basic {token}"})[0] == 401
    assert get(srv.port, headers={"Authorization": token})[0] == 401
    status, headers, body = get(srv.port, headers={"Authorization": f"Bearer {token}"})
    assert status == 200 and json.loads(body) == {"schema": 1}
    assert headers["Content-Type"] == "application/json" and headers["Cache-Control"] == "no-store"
    assert store.take_refused() == 4 and store.take_refused() == 0


def test_only_one_read_only_endpoint(server):
    srv, store, token = server
    auth = {"Authorization": f"Bearer {token}"}
    store.publish({})
    assert get(srv.port, "/", auth)[0] == 404
    assert get(srv.port, "/health", auth)[0] == 404
    assert get(srv.port, API_PATH + "/../x", auth)[0] == 404
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        assert get(srv.port, API_PATH, auth, method)[0] == 501


def test_starting_before_first_snapshot(server):
    srv, _, token = server
    assert get(srv.port, headers={"Authorization": f"Bearer {token}"})[0] == 503


def test_concurrency_is_bounded_and_slow_clients_time_out(server, monkeypatch):
    srv, store, token = server
    store.publish({"ok": True})
    # Two idle connections occupy both slots (max_concurrent=2) until the socket timeout.
    idle = [socket.create_connection(("127.0.0.1", srv.port)) for _ in range(2)]
    time.sleep(0.3)
    with pytest.raises((ConnectionError, http.client.RemoteDisconnected, OSError)):
        get(srv.port, headers={"Authorization": f"Bearer {token}"})
    for s in idle:
        s.close()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if get(srv.port, headers={"Authorization": f"Bearer {token}"})[0] == 200:
                break
        except OSError:
            time.sleep(0.2)
    else:
        pytest.fail("server did not recover after the idle clients went away")


def test_idle_connection_is_dropped_after_timeout(monkeypatch):
    from meshbeacon import api

    monkeypatch.setattr(api, "SOCKET_TIMEOUT", 0.5)
    store = StatusStore(new_token())
    srv = ApiServer(store, "127.0.0.1", 0, max_concurrent=1)
    srv.start()
    try:
        s = socket.create_connection(("127.0.0.1", srv.port))
        s.settimeout(5)
        start = time.monotonic()
        assert s.recv(1) == b""  # server closed the idle connection
        assert time.monotonic() - start < 4
        s.close()
    finally:
        srv.stop()


def test_store_is_thread_safe():
    store = StatusStore(new_token())

    def writer():
        for i in range(500):
            store.publish({"i": i})

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    for _ in range(500):
        body = store.body()
        if body is not None:
            json.loads(body)
    for t in threads:
        t.join()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSupervisor:
    def __init__(self, fail=0, reply=None, delete_error=None):
        self.requests = []
        self.fail = fail
        self.reply = reply if reply is not None else {"result": "ok", "data": {"uuid": "a1b2c3"}}
        self.delete_error = delete_error

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.fail:
            self.fail -= 1
            raise urllib.error.URLError("unreachable")
        if request.get_method() == "DELETE" and self.delete_error:
            raise urllib.error.HTTPError(request.full_url, self.delete_error, "x", {}, None)
        return FakeResponse(json.dumps(self.reply).encode())


def test_discovery_announces_and_remembers_uuid(tmp_path):
    fake = FakeSupervisor()
    d = Discovery("sup-token", tmp_path / "discovery.json", opener=fake)
    assert d.announce("local-meshbeacon", 8100, "api-token")
    req = fake.requests[0]
    assert req.full_url == "http://supervisor/discovery" and req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer sup-token"
    assert json.loads(req.data) == {
        "service": "meshbeacon",
        "config": {"host": "local-meshbeacon", "port": 8100, "token": "api-token"},
    }
    assert json.loads((tmp_path / "discovery.json").read_text()) == {"uuid": "a1b2c3"}
    assert "api-token" not in (tmp_path / "discovery.json").read_text()  # the API token is never on disk


def test_discovery_keeps_trying_until_the_supervisor_answers(tmp_path):
    """Recovery without a MeshBeacon restart (v0.2 review): back-off, then success, then refresh."""
    fake = FakeSupervisor(fail=4)
    stop = threading.Event()
    results = []

    def record(ok):
        results.append(ok)
        if len(results) == 6:
            stop.set()

    d = Discovery("t", tmp_path / "d.json", opener=fake)
    thread = threading.Thread(
        target=d.keep_announced,
        args=("h", 1, "x", stop, record),
        kwargs={"retry_initial": 0.01, "retry_max": 0.04, "reannounce": 0.01},
    )
    thread.start()
    thread.join(10)
    assert not thread.is_alive()
    assert results == [False, False, False, False, True, True]  # refreshes keep going after success
    assert all(json.loads(r.data)["config"]["token"] == "x" for r in fake.requests)


def test_discovery_back_off_is_capped_and_stops_promptly(tmp_path):
    waits = []

    class Stop(threading.Event):
        def wait(self, timeout=None):
            waits.append(timeout)
            if len(waits) >= 8:
                self.set()
            return self.is_set()

    d = Discovery("t", tmp_path / "d.json", opener=FakeSupervisor(fail=100))
    d.keep_announced("h", 1, "x", Stop(), lambda ok: None, retry_initial=30, retry_max=900)
    assert waits == [30, 60, 120, 240, 480, 900, 900, 900]


def test_discovery_withdraw(tmp_path):
    state = tmp_path / "d.json"
    fake = FakeSupervisor()
    d = Discovery("t", state, opener=fake)
    assert d.withdraw() and fake.requests == []  # nothing recorded: nothing to do
    state.write_text('{"uuid": "a1b2c3"}')
    assert d.withdraw()
    assert fake.requests[0].get_method() == "DELETE"
    assert fake.requests[0].full_url == "http://supervisor/discovery/a1b2c3"
    assert not state.exists()
    state.write_text('{"uuid": "../../addons"}')  # never builds a path from unexpected content
    assert d.withdraw() and len(fake.requests) == 1 and not state.exists()
    state.write_text('{"uuid": "abc"}')
    assert Discovery("t", state, opener=FakeSupervisor(delete_error=404)).withdraw()
    state.write_text('{"uuid": "abc"}')
    assert not Discovery("t", state, opener=FakeSupervisor(delete_error=500)).withdraw()
    assert state.exists()


def test_absolute_deadline_ends_trickling_clients(monkeypatch):
    """A client that sends one byte just inside the inactivity timeout cannot hold a slot for ever."""
    store = StatusStore(new_token())
    srv = ApiServer(store, "127.0.0.1", 0, max_concurrent=1, deadline=1.0)
    srv.start()
    try:
        s = socket.create_connection(("127.0.0.1", srv.port))
        start = time.monotonic()
        closed = False
        for _ in range(40):
            try:
                s.sendall(b"G")
            except OSError:
                closed = True
                break
            time.sleep(0.1)
            s.setblocking(False)
            try:
                if s.recv(1) == b"":
                    closed = True
                    break
            except BlockingIOError:
                pass
            finally:
                s.setblocking(True)
        assert closed and time.monotonic() - start < 3
        s.close()
        store.publish({})

        def released():
            try:
                return get(srv.port, headers={"Authorization": "Bearer nope"})[0] == 401
            except OSError:
                return False

        assert any(released() or time.sleep(0.1) for _ in range(30))  # the slot is released
    finally:
        srv.stop()


def test_health_server_is_bounded_but_serves_the_watchdog():
    from meshbeacon.health import HEALTH_DEADLINE, HEALTH_MAX_CONCURRENT, HealthServer, Heartbeat

    srv = HealthServer(Heartbeat(), "127.0.0.1", 0, 60)
    srv.start()
    try:
        assert srv.httpd.slots._initial_value == HEALTH_MAX_CONCURRENT
        assert srv.httpd.deadline == HEALTH_DEADLINE
        idle = [socket.create_connection(("127.0.0.1", srv.port)) for _ in range(HEALTH_MAX_CONCURRENT - 2)]
        assert get(srv.port, "/health")[0] == 200  # spare capacity for the Supervisor's check
        for s in idle:
            s.close()
    finally:
        srv.stop()


def test_tls_certificate_is_fresh_pinned_and_handshake_is_off_the_accept_thread():
    import hashlib
    import os
    import ssl
    import sys
    from pathlib import Path

    from meshbeacon.api import make_tls

    core = Path(__file__).resolve().parents[2] / "meshbeacon" / "core"
    env = {**os.environ, "PYTHONPATH": str(core)}
    tls, fingerprint = make_tls([sys.executable], env)
    _, other = make_tls([sys.executable], env)
    assert fingerprint != other and len(fingerprint) == 64
    store = StatusStore(new_token())
    store.publish({"ok": True})
    srv = ApiServer(store, "127.0.0.1", 0, max_concurrent=3, deadline=2.0, tls=tls)
    srv.start()
    try:
        stalled = socket.create_connection(("127.0.0.1", srv.port))  # never starts the handshake
        client = ssl.create_default_context()
        client.check_hostname = False
        client.verify_mode = ssl.CERT_NONE
        start = time.monotonic()
        with client.wrap_socket(socket.create_connection(("127.0.0.1", srv.port), timeout=5)) as s:
            assert hashlib.sha256(s.getpeercert(binary_form=True)).hexdigest() == fingerprint
            assert s.version() == "TLSv1.3"
        assert time.monotonic() - start < 1.5  # not held up by the stalled client
        stalled.settimeout(5)
        assert stalled.recv(1) == b""  # the stalled handshake is ended by the deadline
        stalled.close()
    finally:
        srv.stop()
