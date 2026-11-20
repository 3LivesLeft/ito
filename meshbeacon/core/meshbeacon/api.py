# SPDX-License-Identifier: Apache-2.0
"""Token-authenticated local API and Supervisor discovery (ADR 0006; messaging: ADRs 0010, 0024).

* Started only when the ``home_assistant_integration`` option is on; otherwise no listener exists.
* Listens on a separate internal port from the watchdog's health endpoint, so that a flood of API
  requests can never starve ``/health``. No port is published.
* ``GET /api/v1/status`` serves a snapshot that the core has already built (the status key).
* ``POST /api/v1/messaging`` (M5) exists only while LXMF messaging is on. It takes a **separate
  messaging key** (the status key is refused there, and the messaging key is refused for status),
  a JSON body of at most 16 KiB, and passes the request to the core's messaging binding, which
  allows only the conversation view's operations. At most ``MESSAGING_CONCURRENT`` messaging
  requests at a time, so that a held long poll never blocks status.
* Bounded: at most ``MAX_CONCURRENT`` requests at a time (others are closed at once), a socket
  inactivity timeout, an absolute per-connection deadline, GET only, no request bodies.
* HTTPS with a throwaway certificate made at every start; Home Assistant pins its fingerprint,
  which it receives only in the discovery message, so another app on the internal network cannot
  read the token or the data, or impersonate MeshBeacon, even with ARP spoofing.
* The bearer token is 256 random bits, created in memory at every start, compared in constant
  time, never written to disk and never logged. It reaches Home Assistant only through Supervisor
  discovery, which only Home Assistant Core can read.
"""

from __future__ import annotations

import contextlib
import hmac
import json
import secrets
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from . import fsutil
from .httpserver import BoundedHTTPServer

API_PATH = "/api/v1/status"
DISCOVERY_SERVICE = "meshbeacon"
SUPERVISOR_URL = "http://supervisor"
MAX_CONCURRENT = 6  # 4 → 6 for M5: messaging takes at most 4, so status always has a slot
MESSAGING_PATH = "/api/v1/messaging"
MESSAGING_CONCURRENT = 4
MAX_BODY = 16 * 1024
SOCKET_TIMEOUT = 5.0  # longest silence from a client
REQUEST_DEADLINE = 10.0  # longest a connection may last, however it trickles
REANNOUNCE_INTERVAL = 6 * 3600.0  # re-send the (unchanged) discovery message; the Supervisor ignores duplicates
RETRY_INITIAL = 30.0
RETRY_MAX = 15 * 60.0


def new_token() -> str:
    return secrets.token_urlsafe(32)


Messaging = Callable[[Any], tuple[int, dict[str, Any]]]


class StatusStore:
    """Thread-safe holder of the latest serialised snapshot and the request counters.

    ``messaging_key`` and ``messaging`` (the core's binding) are set only while LXMF messaging is
    on; without them the messaging endpoint does not exist (404)."""

    def __init__(self, token: str, messaging_key: str | None = None, messaging: Messaging | None = None) -> None:
        self._token = token.encode()
        self._messaging_key = messaging_key.encode() if messaging_key else None
        self.messaging = messaging if messaging_key else None
        self.messaging_slots = threading.BoundedSemaphore(MESSAGING_CONCURRENT)
        self._lock = threading.Lock()
        self._body: bytes | None = None
        self.refused = 0
        self.served = 0

    def publish(self, snapshot: dict[str, Any]) -> None:
        body = json.dumps(snapshot, separators=(",", ":"), allow_nan=False).encode()
        with self._lock:
            self._body = body

    def body(self) -> bytes | None:
        with self._lock:
            return self._body

    def authorised(self, header: str | None, *, messaging: bool = False) -> bool:
        """The bearer key for status, or (``messaging``) the messaging key. Never the other one."""
        expected = self._messaging_key if messaging else self._token
        scheme, _, presented = (header or "").partition(" ")
        ok = (
            expected is not None
            and scheme.lower() == "bearer"
            and hmac.compare_digest(presented.strip().encode(), expected)
        )
        with self._lock:
            if ok:
                self.served += 1
            else:
                self.refused += 1
        return ok

    def take_refused(self) -> int:
        with self._lock:
            count, self.refused = self.refused, 0
            return count


def make_handler(store: StatusStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "MeshBeacon"
        sys_version = ""
        timeout = SOCKET_TIMEOUT  # read when the handler class is made, so tests can shorten it

        def do_GET(self) -> None:
            if self.path != API_PATH:
                self._send(404, b'{"error":"not_found"}')
            elif not store.authorised(self.headers.get("Authorization")):
                self._send(401, b'{"error":"unauthorised"}', {"WWW-Authenticate": "Bearer"})
            elif (body := store.body()) is None:
                self._send(503, b'{"error":"starting"}')
            else:
                self._send(200, body)

        def do_POST(self) -> None:
            if self.path != MESSAGING_PATH or store.messaging is None:
                self._send(404, b'{"error":"not_found"}')
                return
            if not store.authorised(self.headers.get("Authorization"), messaging=True):
                self._send(401, b'{"error":"unauthorised"}', {"WWW-Authenticate": "Bearer"})
                return
            length = self.headers.get("Content-Length", "")
            if not length.isdecimal() or int(length) > MAX_BODY:
                self._send(413, b'{"error":"too_large"}')
                return
            raw = self.rfile.read(int(length))
            if not store.messaging_slots.acquire(blocking=False):
                self._send(503, b'{"error":"busy"}')
                return
            try:
                try:
                    request = json.loads(raw)
                except ValueError:
                    code, answer = 400, {"error": "invalid"}
                else:
                    code, answer = store.messaging(request)
            except Exception:  # never a traceback, never content
                code, answer = 500, {"error": "internal"}
            finally:
                store.messaging_slots.release()
            self._send(code, json.dumps(answer, separators=(",", ":"), allow_nan=False).encode())

        def _send(self, code: int, body: bytes, extra: dict[str, str] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return  # never log requests (they carry the token)

    return Handler


class ApiServer:
    def __init__(
        self,
        store: StatusStore,
        host: str,
        port: int,
        *,
        max_concurrent: int = MAX_CONCURRENT,
        deadline: float = REQUEST_DEADLINE,
        tls: ssl.SSLContext | None = None,
    ) -> None:
        self.httpd = BoundedHTTPServer(
            (host, port), make_handler(store), max_concurrent=max_concurrent, deadline=deadline, tls=tls
        )
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="api", daemon=True)

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


# -- TLS --------------------------------------------------------------------------------------------
class TlsError(Exception):
    pass


def make_tls(python: list[str], env: dict[str, str] | None = None, timeout: float = 60.0) -> tuple[ssl.SSLContext, str]:
    """Create a throwaway certificate in a short-lived process; return a server context and its
    SHA-256 fingerprint. The key exists on disk only for the moment it takes to load it."""
    directory = Path(tempfile.mkdtemp(prefix="meshbeacon-tls-"))
    try:
        directory.chmod(0o700)
        result = subprocess.run(
            [*python, "-m", "meshbeacon.tlscert", "--dir", str(directory)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        if result.returncode != 0:
            raise TlsError("certificate generation failed")
        fingerprint = str(json.loads(result.stdout.strip().splitlines()[-1])["sha256"])
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.load_cert_chain(directory / "cert.pem", directory / "key.pem")
    except (OSError, ValueError, KeyError, IndexError, ssl.SSLError, subprocess.SubprocessError) as exc:
        raise TlsError(type(exc).__name__) from exc
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise TlsError("unexpected fingerprint")
    return context, fingerprint


# -- Supervisor discovery ------------------------------------------------------------------------
Opener = Callable[[urllib.request.Request, float], Any]


def _open(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - fixed http://supervisor URL


# The relay runs as root; the core accepts a link only to root (tests may change this).
RELAY_PEER_UID = 0


class RelayRefusedError(OSError):
    """The discovery relay refused or could not deliver a request."""


class RelayLink:
    """The core's one connection to the root discovery relay (discovery_relay.py, M1.2).

    The core never opens it: its root start step (relay_link.py) connects and passes the descriptor
    in ``MESHBEACON_RELAY_FD``. It is made non-inheritable at once and child processes are started
    with ``close_fds``, so the Reticulum child never holds it (threat T72). If it breaks, it stays
    broken until the app restarts; the integration keeps its key until then, because the key only
    changes at an app start.
    """

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._lock = threading.Lock()
        self.broken = False

    @classmethod
    def from_fd(cls, fd: int) -> RelayLink | None:
        """Adopt descriptor ``fd`` if, and only if, it is a Unix stream connection to root."""
        try:
            sock = socket.socket(fileno=fd)
        except OSError:
            return None
        if sock.family != socket.AF_UNIX or sock.type != socket.SOCK_STREAM or _peer_uid(sock) != RELAY_PEER_UID:
            sock.close()
            return None
        sock.set_inheritable(False)
        sock.settimeout(None)
        return cls(sock)

    def request(self, request: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
        with self._lock:
            if self.broken:
                raise RelayRefusedError("link lost")
            try:
                self._sock.settimeout(timeout)
                self._sock.sendall(json.dumps(request).encode() + b"\n")
                data = b""
                while b"\n" not in data:
                    chunk = self._sock.recv(4096)
                    if not chunk or len(data) + len(chunk) > 65536:
                        raise OSError("no reply")
                    data += chunk
            except OSError as exc:  # a half-read reply would put later replies out of step
                self.broken = True
                self._sock.close()
                raise RelayRefusedError("link lost") from exc
        try:
            value = json.loads(data.split(b"\n", 1)[0])
        except ValueError as exc:
            raise RelayRefusedError("bad reply") from exc
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise RelayRefusedError(str(value.get("error", "refused")) if isinstance(value, dict) else "refused")
        return value

    def close(self) -> None:
        with self._lock:
            self.broken = True
            self._sock.close()


def _peer_uid(sock: socket.socket) -> int | None:
    try:
        creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    except OSError:
        return None
    return int(struct.unpack("3i", creds)[1])


class Discovery:
    """Announces the API to Home Assistant through the Supervisor (no ``hassio_api`` needed).

    Two transports, chosen by the caller (``Supervisor.setup_integration``):

    - **Socket** (preferred, newer Supervisors): ``relay`` is the core's link to the root discovery
      relay, which reaches the Supervisor over its per-app Unix socket. Nothing crosses the internal
      network, and no token exists in the core.
    - **Compatibility path** (Supervisor 2026.11.0 and older): HTTP to ``http://supervisor`` on the
      internal network with the Supervisor token (risk RR-9a in the threat model).

    The UUID of the message (not secret) is remembered in ``state_path`` so that the message can be
    withdrawn when the user switches the integration option off.
    """

    def __init__(
        self,
        supervisor_token: str | None,
        state_path: Path,
        *,
        base_url: str = SUPERVISOR_URL,
        opener: Opener = _open,
        timeout: float = 10.0,
        relay: RelayLink | None = None,
    ) -> None:
        if relay is None and not supervisor_token:
            raise ValueError("discovery needs either the relay or a Supervisor token")
        self._supervisor_token = supervisor_token
        self.state_path = state_path
        self.base_url = base_url
        self.opener = opener
        self.timeout = timeout
        self.relay = relay

    @property
    def transport(self) -> str:
        return "socket" if self.relay is not None else "tcp"

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.relay is not None:
            return self._relay_request(method, path, payload)
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(  # noqa: S310 - fixed http://supervisor URL
            self.base_url + path,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self._supervisor_token}", "Content-Type": "application/json"},
        )
        with self.opener(request, self.timeout) as response:
            raw = response.read(65536)
        value = json.loads(raw) if raw else {}
        return value if isinstance(value, dict) else {}

    def _relay_request(self, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        """The same two requests, through the relay (which rebuilds and validates them)."""
        if self.relay is None:
            raise ValueError("no relay")
        if method == "POST" and path == "/discovery" and payload is not None:
            reply = self.relay.request({"op": "announce", "config": payload.get("config")}, self.timeout + 5)
            return {"data": {"uuid": reply.get("uuid")}}
        if method == "DELETE" and path.startswith("/discovery/"):
            self.relay.request({"op": "withdraw", "uuid": path.removeprefix("/discovery/")}, self.timeout + 5)
            return {}
        raise ValueError("unsupported discovery request")

    def announce(self, host: str, port: int, api_token: str, cert_sha256: str = "", messaging_key: str = "") -> bool:
        """One attempt to send (or refresh) the discovery message.

        ``messaging_key`` (M5) only while LXMF messaging is on. On the compatibility path it crosses
        the internal network like the status key: an accepted risk (ADR 0024, RR-9b)."""
        config: dict[str, Any] = {"host": host, "port": port, "token": api_token}
        if cert_sha256:
            config["cert_sha256"] = cert_sha256
        if messaging_key and cert_sha256:  # never without TLS
            config["messaging_key"] = messaging_key
        payload = {"service": DISCOVERY_SERVICE, "config": config}
        try:
            reply = self._request("POST", "/discovery", payload)
        except (OSError, ValueError, urllib.error.URLError):
            return False
        uuid = (reply.get("data") or {}).get("uuid")
        if isinstance(uuid, str):
            with contextlib.suppress(OSError):
                fsutil.atomic_write_json(self.state_path, {"uuid": uuid})
        return True

    def keep_announced(
        self,
        host: str,
        port: int,
        api_token: str,
        stop: threading.Event,
        on_result: Callable[[bool], None],
        *,
        cert_sha256: str = "",
        messaging_key: str = "",
        retry_initial: float = RETRY_INITIAL,
        retry_max: float = RETRY_MAX,
        reannounce: float = REANNOUNCE_INTERVAL,
    ) -> None:
        """Announce until it succeeds, with back-off, then refresh it now and then — for ever.

        Recovers by itself from a Supervisor that is restarting or briefly unreachable, without a
        restart of MeshBeacon. Refreshing re-sends the same message; the Supervisor ignores an exact
        duplicate, so Home Assistant is not disturbed.
        """
        delay = retry_initial
        while not stop.is_set():
            ok = self.announce(host, port, api_token, cert_sha256, messaging_key)
            on_result(ok)
            if self.relay is not None and self.relay.broken:
                return  # a lost relay link cannot come back until the app restarts (MSG_RELAY_LOST)
            if ok:
                delay = retry_initial
                stop.wait(reannounce)
            else:
                stop.wait(delay)
                delay = min(delay * 2, retry_max)

    def withdraw(self) -> bool:
        """Remove a previously sent message, if one was recorded. True if nothing remains to do."""
        state = fsutil.read_json(self.state_path)
        uuid = state.get("uuid") if isinstance(state, dict) else None
        if not isinstance(uuid, str) or not uuid.isalnum():
            self.state_path.unlink(missing_ok=True)
            return True
        try:
            self._request("DELETE", f"/discovery/{uuid}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:  # already gone counts as done
                return False
        except (OSError, ValueError):
            return False
        self.state_path.unlink(missing_ok=True)
        return True


def container_hostname() -> str:
    """The app's hostname on the Supervisor's internal network (slug with '-'), e.g. local-meshbeacon."""
    return socket.gethostname()
