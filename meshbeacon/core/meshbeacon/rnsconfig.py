# SPDX-License-Identifier: Apache-2.0
"""Injection-safe rendering of the Reticulum configuration file (architecture §4.1).

The file is built with ConfigObj's object API — the same parser Reticulum uses to read it — and
never by string templating. User input only ever becomes a section name or a value, both of which
have already passed allow-list validation, and the rendered text is re-parsed and compared with
the intended structure before it is used.
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Any

from .settings import Settings

LOGLEVELS = {"quiet": 2, "normal": 4, "detailed": 5}
INSTANCE_NAME = "meshbeacon"
# The shared instance's RPC key while messaging is on (ADR 0023): created by the root init step at
# every container start, root:mb-rpc 0640, so that only Reticulum's user (for the node's
# configuration) and the messaging engine's user (for its client configuration) can read it.
# RNS 1.6.0 authenticates every local RPC client with this one key (multiprocessing.connection
# authkey, RNS/Reticulum.py ``get_rpc_client``); a client without it derives a key of its own from
# its own transport identity, which the node refuses ("digest received was wrong").
RPC_KEY_FILE = Path(os.environ.get("MESHBEACON_RPC_KEY_FILE", "/run/meshbeacon-rpc/rpc_key"))
_RPC_KEY = re.compile(r"[0-9a-f]{64}")

# Keys that MeshBeacon must never render in v0.1 (privacy defaults). Checked after rendering.
FORBIDDEN_KEYS = frozenset(
    {
        "discover_interfaces",
        "autoconnect_discovered_interfaces",
        "discoverable",
        "publish_ifac",
        "location_cmd",
        "reachable_on",
        "listen_ip",
        "listen_port",
    }
)
ALLOWED_INTERFACE_TYPES = frozenset({"TCPClientInterface"})


class RenderError(Exception):
    pass


def new_rpc_key() -> str:
    """A fresh, random RPC key (hex), independent of the identity (RNS would otherwise derive it)."""
    key = secrets.token_hex(32)
    bytes.fromhex(key)  # RNS reads rpc_key with bytes.fromhex and silently falls back if invalid
    return key


def read_shared_rpc_key(path: Path | None = None) -> str | None:
    """The shared RPC key, or None if it is missing, unreadable or not exactly 64 hex digits."""
    try:
        with open(path or RPC_KEY_FILE, "rb") as handle:
            text = handle.read(128).decode("ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return text if _RPC_KEY.fullmatch(text) else None


def intended_structure(settings: Settings, rpc_key: str, *, share_instance: bool = False) -> dict[str, Any]:
    """``share_instance`` only when the user has switched messaging on (M4, D-M4-8, IS-3a)."""
    bytes.fromhex(rpc_key)
    interfaces: dict[str, dict[str, str]] = {}
    for peer in settings.peers:
        section = {
            "type": "TCPClientInterface",
            "enabled": "yes",
            "target_host": peer.host,
            "target_port": str(peer.port),
        }
        if peer.network_name:
            section["network_name"] = peer.network_name
        if peer.passphrase:
            section["passphrase"] = peer.passphrase
        interfaces[peer.name] = section
    reticulum = {
        "enable_transport": "Yes" if settings.transport else "No",
        # No shared instance: no local sockets and no RPC listener are opened (verified).
        # With messaging switched on, the engine connects as a client of the shared instance and
        # authenticates its RPC requests with the same key (ADR 0023, amending IS-3a).
        "share_instance": "Yes" if share_instance else "No",
        "instance_name": INSTANCE_NAME,
        "rpc_key": rpc_key,
        "panic_on_interface_error": "No",
    }
    if share_instance:
        # The one RPC capability the engine has no use for at all: attaching, detaching and
        # reloading the node's interfaces (RNS/Reticulum.py ``_attach_interface``; RNS's own
        # internal calls are not affected). Refused over RPC while the instance is shared.
        reticulum["enable_interface_management"] = "No"
    return {
        "reticulum": reticulum,
        "logging": {"loglevel": str(LOGLEVELS[settings.log_level])},
        "interfaces": interfaces,
    }


def _configobj() -> Any:
    # The parser vendored by RNS, so that rendering and verification use exactly the parser
    # Reticulum will use. Imported lazily: only the short-lived prepare process needs it.
    from RNS.vendor.configobj import ConfigObj

    return ConfigObj


def _to_plain(section: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in section.scalars:
        out[key] = section[key]  # item access applies interpolation, as RNS's reads do
    for key in section.sections:
        out[key] = _to_plain(section[key])
    return out


def _check_forbidden(structure: dict[str, Any]) -> None:
    """Refuse forbidden *settings* anywhere. Peer names are section names, not settings."""
    blocks: list[dict[str, Any]] = [structure.get("reticulum", {}), structure.get("logging", {})]
    blocks.extend(v for v in structure.get("interfaces", {}).values() if isinstance(v, dict))
    for block in blocks:
        for key, value in block.items():
            if key in FORBIDDEN_KEYS or isinstance(value, dict):
                raise RenderError(f"refusing to render forbidden key {key!r}")
    if set(structure) != {"reticulum", "logging", "interfaces"}:
        raise RenderError("unexpected top-level section")
    for iface in structure.get("interfaces", {}).values():
        if not isinstance(iface, dict) or iface.get("type") not in ALLOWED_INTERFACE_TYPES:
            raise RenderError("refusing to render an interface type that v0.1 does not allow")


def render(settings: Settings, rpc_key: str, *, share_instance: bool = False) -> str:
    """Return the configuration text, verified to parse back to exactly the intended structure."""
    expected = intended_structure(settings, rpc_key, share_instance=share_instance)
    _check_forbidden(expected)
    return _write(expected)


def client_structure(loglevel: str = "quiet", rpc_key: str | None = None) -> dict[str, Any]:
    """The messaging engine's own configuration: a client of the node's shared instance only.

    No interfaces and no transport; ``instance_name`` must match the node's. ``rpc_key`` is the
    node's shared RPC key (ADR 0023). RNS 1.6.0 clients need it for ordinary operation, not just
    for control: every recall of a known destination reports its use to the node, LXMF checks
    each sender against the node's blackhole list, link identifications are checked the same way,
    and LXMF registers the destination types it needs (RNS/Reticulum.py ``_used_destination_data``,
    ``is_blackholed``, ``wants_destination_type``). Without the key each of these is refused.
    """
    reticulum = {
        "enable_transport": "No",
        "share_instance": "Yes",
        "instance_name": INSTANCE_NAME,
        "panic_on_interface_error": "No",
    }
    if rpc_key is not None:
        if not _RPC_KEY.fullmatch(rpc_key):
            raise RenderError("invalid RPC key")
        reticulum["rpc_key"] = rpc_key
    return {
        "reticulum": reticulum,
        "logging": {"loglevel": str(LOGLEVELS[loglevel])},
        "interfaces": {},
    }


def render_client(loglevel: str = "quiet", *, instance_name: str = INSTANCE_NAME, rpc_key: str | None = None) -> str:
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", instance_name):
        raise RenderError("invalid instance name")
    expected = client_structure(loglevel, rpc_key)
    expected["reticulum"]["instance_name"] = instance_name  # tests use a name of their own
    _check_forbidden(expected)
    return _write(expected)


def _write(expected: dict[str, Any]) -> str:
    config_obj = _configobj()
    cfg = config_obj()
    cfg.initial_comment = [
        "# Generated by MeshBeacon on every start. Do not edit: changes are overwritten.",
    ]
    for section, values in expected.items():
        cfg[section] = {}
        for key, value in values.items():
            cfg[section][key] = value
    lines = cfg.write()
    text = "\n".join(lines) + "\n"
    verify(text, expected)
    return text


def verify(text: str, expected: dict[str, Any]) -> None:
    """Re-parse ``text`` as RNS will and require a structurally identical result."""
    config_obj = _configobj()
    try:
        parsed = config_obj(text.splitlines())
        plain = _to_plain(parsed)
    except Exception as exc:  # any parser complaint means the text is not what we intended
        raise RenderError(f"rendered configuration does not parse: {type(exc).__name__}") from exc
    if plain != expected:
        raise RenderError("rendered configuration does not match the intended structure")
    _check_forbidden(plain)
