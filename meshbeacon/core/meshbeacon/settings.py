# SPDX-License-Identifier: Apache-2.0
"""Typed, allow-list validation of user options (architecture §4.1).

Every user-controlled value is validated here before it can reach the Reticulum configuration.
Validation is authoritative: the Supervisor schema in ``config.yaml`` is only a first layer.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from . import networks

LogLevel = Literal["quiet", "normal", "detailed"]
LOG_LEVELS: tuple[LogLevel, ...] = ("quiet", "normal", "detailed")

MAX_PEERS = 10
MEMORY_LIMIT_MIN_MB = 128
MEMORY_LIMIT_MAX_MB = 1024
MEMORY_LIMIT_DEFAULT_MB = 256

# A peer name becomes a ConfigObj section name, so it must not contain brackets, quotes, "#",
# "=", "%", "$", commas or control characters, and must not start or end with a space.
_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 _.-]{0,30}[A-Za-z0-9_.-])?$")
_LABEL_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
# Passphrases: printable ASCII except characters with meaning to ConfigObj (quotes, "#", ",",
# "\") or to its interpolation ("%", "$"). No leading or trailing space.
_PASSPHRASE_FORBIDDEN = set("\"'#,%$\\")

ALLOWED_TOP_LEVEL = {
    "network",
    "peers",
    "transport",
    "log_level",
    "memory_limit_mb",
    "replace_identity",
    "home_assistant_integration",
    "messaging_enabled",
    "messaging_display_name",
    "messaging_contacts",
    "messaging_accept_anyone",
    "messaging_auto_reply",
    "messaging_propagation_node",
}
ALLOWED_PEER_KEYS = {"name", "host", "port", "network_name", "passphrase"}
ALLOWED_CONTACT_KEYS = {"name", "address"}
MAX_CONTACTS = 20
# An LXMF address (a destination hash): 32 hexadecimal characters. Shown to the user as such.
_ADDRESS_RE = re.compile(r"^[0-9a-fA-F]{32}$")


class ValidationError(Exception):
    """Raised with one or more plain-language problems in the options."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Peer:
    name: str
    host: str
    port: int
    network_name: str | None = None
    passphrase: str | None = None


@dataclass(frozen=True)
class Contact:
    """A messaging contact: a label the user chose and the contact's LXMF address."""

    name: str
    address: str  # 32 lower-case hex characters


@dataclass(frozen=True)
class Messaging:
    """The optional LXMF messaging engine (M4, D-M4-8): off unless the user ticks the box."""

    enabled: bool = False
    display_name: str = ""
    contacts: tuple[Contact, ...] = ()
    accept_anyone: bool = False
    auto_reply: bool = True
    propagation_node: str | None = None


@dataclass(frozen=True)
class Settings:
    # Every Reticulum interface to configure: the selected public network (if any) first, then
    # the user's own peers. ``network`` is the selected preset id, or ``custom``.
    peers: tuple[Peer, ...] = ()
    network: str = networks.CUSTOM
    transport: bool = False
    log_level: LogLevel = "normal"
    memory_limit_mb: int = MEMORY_LIMIT_DEFAULT_MB
    replace_identity: bool = False
    home_assistant_integration: bool = False
    messaging: Messaging = field(default_factory=Messaging)

    @property
    def secrets(self) -> tuple[str, ...]:
        """Values that must never appear in logs."""
        return tuple(p.passphrase for p in self.peers if p.passphrase)


def _has_control(value: str) -> bool:
    return any(ord(ch) < 0x20 or ord(ch) == 0x7F or 0x80 <= ord(ch) <= 0x9F for ch in value) or any(
        ch in value for ch in ("\u2028", "\u2029", "\u202e", "\ufeff")
    )


def valid_name(value: str) -> bool:
    return value.isascii() and not _has_control(value) and bool(_NAME_RE.match(value))


def valid_host(value: str) -> bool:
    """A DNS hostname (RFC 1123, ASCII only) or an IPv4/IPv6 literal without a zone or port."""
    if not value or not value.isascii() or _has_control(value) or len(value) > 253:
        return False
    if "%" in value or "/" in value:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    if value.endswith(".") or ":" in value:
        return False
    labels = value.split(".")
    if all(label.isdigit() for label in labels):
        return False  # looks like a malformed IPv4 address
    return all(_LABEL_RE.match(label) for label in labels)


def valid_passphrase(value: str) -> bool:
    if not (1 <= len(value) <= 128) or not value.isascii():
        return False
    if value != value.strip(" "):
        return False
    return all(0x20 <= ord(ch) <= 0x7E and ch not in _PASSPHRASE_FORBIDDEN for ch in value)


def _bool(raw: dict[str, Any], key: str, default: bool, problems: list[str]) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        problems.append(f"'{key}' must be on or off.")
        return default
    return value


def _address(value: Any) -> str | None:
    """An LXMF address as the user may paste it (spaces and angle brackets around it are fine)."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().strip("<>").strip()
    return cleaned.lower() if _ADDRESS_RE.match(cleaned) else None


def _parse_messaging(raw: dict[str, Any], problems: list[str]) -> Messaging:
    enabled = _bool(raw, "messaging_enabled", False, problems)
    accept_anyone = _bool(raw, "messaging_accept_anyone", False, problems)
    auto_reply = _bool(raw, "messaging_auto_reply", True, problems)
    display = raw.get("messaging_display_name") or ""
    if not isinstance(display, str) or (display and not valid_name(display)):
        problems.append(
            "Messaging: the display name must be 1–32 letters, digits, spaces, dots, dashes or "
            "underscores, starting with a letter or digit (or left empty)."
        )
        display = ""
    node_raw = raw.get("messaging_propagation_node") or None
    node = _address(node_raw) if node_raw is not None else None
    if node_raw is not None and node is None:
        problems.append("Messaging: the propagation node must be an LXMF address of 32 hexadecimal characters.")
    contacts: list[Contact] = []
    items = raw.get("messaging_contacts", [])
    if not isinstance(items, list):
        problems.append("'messaging_contacts' must be a list.")
        items = []
    elif len(items) > MAX_CONTACTS:
        problems.append(f"At most {MAX_CONTACTS} messaging contacts can be configured.")
        items = []
    names: set[str] = set()
    addresses: set[str] = set()
    for index, item in enumerate(items):
        where = f"Messaging contact {index + 1}"
        if not isinstance(item, dict) or set(item) - ALLOWED_CONTACT_KEYS:
            problems.append(f"{where} is not in the expected format (a name and an address).")
            continue
        name, address = item.get("name"), _address(item.get("address"))
        if not isinstance(name, str) or not valid_name(name):
            problems.append(
                f"{where}: the name must be 1–32 letters, digits, spaces, dots, dashes or underscores, "
                "starting with a letter or digit."
            )
            continue
        if address is None:
            problems.append(
                f"Messaging contact '{name}': the address must be the contact's LXMF address, 32 hexadecimal "
                "characters, as the contact's LXMF app shows it."
            )
            continue
        if name.casefold() in names:
            problems.append(f"Two messaging contacts are called '{name}'. Each needs a different name.")
            continue
        if address in addresses:
            problems.append(f"Messaging contact '{name}' has the same address as another contact.")
            continue
        names.add(name.casefold())
        addresses.add(address)
        contacts.append(Contact(name, address))
    return Messaging(enabled, display, tuple(contacts), accept_anyone, auto_reply, node)


def _parse_peer(index: int, raw: Any, problems: list[str]) -> Peer | None:
    where = f"Peer {index + 1}"
    if not isinstance(raw, dict):
        problems.append(f"{where} is not in the expected format.")
        return None
    unknown = set(raw) - ALLOWED_PEER_KEYS
    if unknown:
        problems.append(f"{where} has unknown settings: {', '.join(sorted(map(str, unknown)))}.")
        return None

    name = raw.get("name")
    host = raw.get("host")
    port = raw.get("port")
    network_name = raw.get("network_name") or None
    passphrase = raw.get("passphrase") or None
    ok = True

    if not isinstance(name, str) or not valid_name(name):
        problems.append(
            f"{where}: the name must be 1–32 letters, digits, spaces, dots, dashes or underscores, "
            "starting with a letter or digit."
        )
        ok = False
    else:
        where = f"Peer '{name}'"
    if not isinstance(host, str) or not valid_host(host):
        problems.append(f"{where}: the host must be a hostname such as rns.example.org, or an IP address.")
        ok = False
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        problems.append(f"{where}: the port must be a number between 1 and 65535.")
        ok = False
    if network_name is not None and (not isinstance(network_name, str) or not valid_name(network_name)):
        problems.append(f"{where}: the network name uses characters that are not allowed.")
        ok = False
    if passphrase is not None and (not isinstance(passphrase, str) or not valid_passphrase(passphrase)):
        problems.append(
            f"{where}: the passphrase must be 1–128 plain characters and must not contain quotes, "
            "#, comma, %, $, backslash or leading/trailing spaces."
        )
        ok = False
    if not ok or not isinstance(name, str) or not isinstance(host, str) or not isinstance(port, int):
        return None
    return Peer(name=name, host=host, port=port, network_name=network_name, passphrase=passphrase)


def _apply_network(value: Any, peers: list[Peer], problems: list[str]) -> tuple[str, list[Peer]]:
    """Add the selected public network as the first peer (ADR 0004; ``custom`` adds none).

    If the user already has a peer with the same host and port (for example one they typed in
    before the selector existed), theirs is kept as it is and the preset is not added twice.
    """
    if value is None or value == "":
        value = networks.CUSTOM
    if not isinstance(value, str) or value not in networks.choices():
        problems.append("'network' must be one of: " + ", ".join(networks.choices()) + ".")
        return networks.CUSTOM, peers
    preset = networks.presets().get(value)
    if preset is None:
        return value, peers
    if any(p.host.casefold() == preset.host and p.port == preset.port for p in peers):
        return value, peers
    if any(p.name.casefold() == preset.name.casefold() for p in peers):
        problems.append(
            f"One of your own peers is called '{preset.name}', the same as the public network you "
            "selected. Rename that peer, or remove it."
        )
        return value, peers
    return value, [Peer(name=preset.name, host=preset.host, port=preset.port), *peers]


def parse_options(raw: Any) -> Settings:
    """Validate the Supervisor ``options.json`` content and return typed settings."""
    if not isinstance(raw, dict):
        raise ValidationError(["The app options are not in the expected format."])
    problems: list[str] = []
    unknown = set(raw) - ALLOWED_TOP_LEVEL
    if unknown:
        problems.append(f"Unknown options: {', '.join(sorted(map(str, unknown)))}.")

    peers_raw = raw.get("peers", [])
    peers: list[Peer] = []
    if not isinstance(peers_raw, list):
        problems.append("'peers' must be a list.")
    elif len(peers_raw) > MAX_PEERS:
        problems.append(f"At most {MAX_PEERS} peers can be configured.")
    else:
        for i, item in enumerate(peers_raw):
            peer = _parse_peer(i, item, problems)
            if peer is not None:
                peers.append(peer)
        seen: set[str] = set()
        for peer in peers:
            key = peer.name.casefold()
            if key in seen:
                problems.append(f"Two peers are called '{peer.name}'. Each peer needs a different name.")
            seen.add(key)

    network, peers = _apply_network(raw.get("network", networks.CUSTOM), peers, problems)

    log_level = raw.get("log_level", "normal")
    if log_level not in LOG_LEVELS:
        problems.append("'log_level' must be quiet, normal or detailed.")
        log_level = "normal"

    memory = raw.get("memory_limit_mb", MEMORY_LIMIT_DEFAULT_MB)
    if (
        isinstance(memory, bool)
        or not isinstance(memory, int)
        or not (MEMORY_LIMIT_MIN_MB <= memory <= MEMORY_LIMIT_MAX_MB)
    ):
        problems.append(f"'memory_limit_mb' must be a number between {MEMORY_LIMIT_MIN_MB} and {MEMORY_LIMIT_MAX_MB}.")
        memory = MEMORY_LIMIT_DEFAULT_MB

    transport = _bool(raw, "transport", False, problems)
    replace_identity = _bool(raw, "replace_identity", False, problems)
    integration = _bool(raw, "home_assistant_integration", False, problems)
    messaging = _parse_messaging(raw, problems)

    if problems:
        raise ValidationError(problems)
    return Settings(
        peers=tuple(peers),
        network=network,
        transport=transport,
        log_level=log_level,
        memory_limit_mb=memory,
        replace_identity=replace_identity,
        home_assistant_integration=integration,
        messaging=messaging,
    )
