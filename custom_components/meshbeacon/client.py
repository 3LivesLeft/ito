# SPDX-License-Identifier: Apache-2.0
"""Client and schema validation for MeshBeacon's local status API (schema 1, ADR 0006).

The integration never imports Reticulum or the MeshBeacon core. Everything it knows about the
app comes through this one versioned, validated interface. Values the app reports as unavailable
(``null``) stay ``None`` and are shown as "unknown" in Home Assistant, never as zero.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import CONNECTIVITY, PROBLEMS, REQUEST_TIMEOUT, SCHEMA_VERSION, STATES

API_PATH = "/api/v1/status"
MAX_PEERS = 10
MAX_RESPONSE = 256 * 1024


class MeshBeaconError(Exception):
    """The app could not be reached or returned something unusable."""


class AuthError(MeshBeaconError):
    """The app refused the token (it changes at every app start; rediscovery brings the new one)."""


class SchemaError(MeshBeaconError):
    """The response does not match the schema this integration understands."""


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _int(value: Any) -> int | None:
    number = _num(value)
    return None if number is None else int(number)


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _text(value: Any, limit: int = 2000) -> str | None:
    return value[:limit] if isinstance(value, str) else None


def _enum(value: Any, allowed: tuple[str, ...], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise SchemaError(f"missing section {key!r}")
    return value


@dataclass(frozen=True)
class Peer:
    name: str
    connected: bool
    connected_since: float | None
    rx_bytes: int | None
    tx_bytes: int | None
    rx_rate: float | None
    tx_rate: float | None
    announces_rx: int | None
    announces_tx: int | None
    reconnections: int | None


@dataclass(frozen=True)
class Status:
    generated_at: float | None
    version: str | None
    rns_version: str | None
    arch: str | None
    state: str
    connectivity: str
    problem: str
    message: str | None
    app_started_at: float | None
    running: bool | None
    reticulum_started_at: float | None
    transport_enabled: bool | None
    restarts: int | None
    memory_restarts: int | None
    peers_configured: int | None
    peers_connected: int | None
    rx_bytes: int | None
    tx_bytes: int | None
    rx_rate: float | None
    tx_rate: float | None
    packets_rx: int | None
    packets_tx: int | None
    paths: int | None
    relayed_links: int | None
    announces_rx: int | None
    announces_tx: int | None
    memory_bytes: int | None
    core_memory_bytes: int | None
    reticulum_memory_bytes: int | None
    cpu_percent: float | None
    peers: tuple[Peer, ...]

    def peer(self, name: str) -> Peer | None:
        return next((p for p in self.peers if p.name == name), None)


def parse_status(data: Any) -> Status:
    """Validate a decoded response. Unknown fields are ignored; unusable values become None."""
    if not isinstance(data, dict):
        raise SchemaError("response is not an object")
    if data.get("schema") != SCHEMA_VERSION:
        raise SchemaError(f"unsupported schema {data.get('schema')!r}")
    app, node, net, res = (_section(data, k) for k in ("app", "node", "network", "resources"))
    peers_raw = data.get("peers")
    if not isinstance(peers_raw, list):
        raise SchemaError("missing peers")
    peers: list[Peer] = []
    seen: set[str] = set()
    for item in peers_raw[:MAX_PEERS]:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"), 32)
        if not name or name in seen:
            continue
        seen.add(name)
        peers.append(
            Peer(
                name=name,
                connected=item.get("connected") is True,
                connected_since=_num(item.get("connected_since")),
                rx_bytes=_int(item.get("rx_bytes")),
                tx_bytes=_int(item.get("tx_bytes")),
                rx_rate=_num(item.get("rx_rate")),
                tx_rate=_num(item.get("tx_rate")),
                announces_rx=_int(item.get("announces_rx")),
                announces_tx=_int(item.get("announces_tx")),
                reconnections=_int(item.get("reconnections")),
            )
        )
    cpu = _num(res.get("cpu_percent"))
    return Status(
        generated_at=_num(data.get("generated_at")),
        version=_text(app.get("version"), 32),
        rns_version=_text(app.get("rns_version"), 32),
        arch=_text(app.get("arch"), 32),
        state=_enum(app.get("state"), STATES, "starting"),
        connectivity=_enum(app.get("connectivity"), CONNECTIVITY, "unknown"),
        problem=_enum(app.get("problem"), PROBLEMS, "unexpected" if app.get("problem") else "none"),
        message=_text(app.get("message")),
        app_started_at=_num(app.get("started_at")),
        running=_bool(node.get("running")),
        reticulum_started_at=_num(node.get("started_at")),
        transport_enabled=_bool(node.get("transport_enabled")),
        restarts=_int(node.get("restarts")),
        memory_restarts=_int(node.get("memory_restarts")),
        peers_configured=_int(net.get("peers_configured")),
        peers_connected=_int(net.get("peers_connected")),
        rx_bytes=_int(net.get("rx_bytes")),
        tx_bytes=_int(net.get("tx_bytes")),
        rx_rate=_num(net.get("rx_rate")),
        tx_rate=_num(net.get("tx_rate")),
        packets_rx=_int(net.get("packets_rx")),
        packets_tx=_int(net.get("packets_tx")),
        paths=_int(net.get("paths")),
        relayed_links=_int(net.get("relayed_links")),
        announces_rx=_int(net.get("announces_rx")),
        announces_tx=_int(net.get("announces_tx")),
        memory_bytes=_int(res.get("memory_bytes")),
        core_memory_bytes=_int(res.get("core_memory_bytes")),
        reticulum_memory_bytes=_int(res.get("reticulum_memory_bytes")),
        cpu_percent=None if cpu is None else min(cpu, 100.0 * 64),
        peers=tuple(peers),
    )


class MeshBeaconClient:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, token: str, cert_sha256: str) -> None:
        """HTTPS pinned to ``cert_sha256``: the certificate is not trusted through any authority, only
        by its fingerprint from the discovery message. aiohttp checks it before sending the key."""
        self._session = session
        self._url = f"https://{host}:{int(port)}{API_PATH}"
        self._token = token
        self._ssl = aiohttp.Fingerprint(bytes.fromhex(cert_sha256))

    async def async_get_status(self) -> Status:
        try:
            async with self._session.get(
                self._url,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                allow_redirects=False,
                ssl=self._ssl,
            ) as response:
                if response.status == 401:
                    raise AuthError("token refused")
                if response.status != 200:
                    raise MeshBeaconError(f"HTTP {response.status}")
                body = await response.content.read(MAX_RESPONSE + 1)
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise MeshBeaconError(type(exc).__name__) from exc
        if len(body) > MAX_RESPONSE:
            raise SchemaError("response too large")
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise SchemaError("response is not JSON") from exc
        return parse_status(data)
