# SPDX-License-Identifier: Apache-2.0
"""Injection-safe rendering of the Reticulum configuration file (architecture §4.1).

The file is built with ConfigObj's object API — the same parser Reticulum uses to read it — and
never by string templating. User input only ever becomes a section name or a value, both of which
have already passed allow-list validation, and the rendered text is re-parsed and compared with
the intended structure before it is used.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from .settings import Settings

LOGLEVELS = {"quiet": 2, "normal": 4, "detailed": 5}
INSTANCE_NAME = "meshbeacon"

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
    return {
        "reticulum": {
            "enable_transport": "Yes" if settings.transport else "No",
            # No shared instance: no local sockets and no RPC listener are opened (verified).
            # With messaging switched on, the engine connects as a client of the shared instance;
            # the RPC listener needs this key, which the engine never has (IS-3a).
            "share_instance": "Yes" if share_instance else "No",
            "instance_name": INSTANCE_NAME,
            "rpc_key": rpc_key,
            "panic_on_interface_error": "No",
        },
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


def client_structure(loglevel: str = "quiet") -> dict[str, Any]:
    """The messaging engine's own configuration: a client of the node's shared instance only.

    No interfaces and no transport; ``instance_name`` must match the node's. No RPC key: the
    engine has no business controlling the node (IS-3a). Verified with RNS 1.6.0 and LXMF 1.3.0
    (tests/integration/test_messaging_lxmf.py): sending, receiving and propagation all work
    without it. RNS then logs failed "destination used" updates (RNS/Reticulum.py
    ``_used_destination_data``) and drops link identifications it cannot check against the
    node's blackhole list (RNS/Link.py, ``is_blackholed``), which fails closed.
    """
    return {
        "reticulum": {
            "enable_transport": "No",
            "share_instance": "Yes",
            "instance_name": INSTANCE_NAME,
            "panic_on_interface_error": "No",
        },
        "logging": {"loglevel": str(LOGLEVELS[loglevel])},
        "interfaces": {},
    }


def render_client(loglevel: str = "quiet", *, instance_name: str = INSTANCE_NAME) -> str:
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", instance_name):
        raise RenderError("invalid instance name")
    expected = client_structure(loglevel)
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
