# SPDX-License-Identifier: Apache-2.0
"""Typed, allow-list validation of user options (architecture §4.1).

Every user-controlled value is validated here before it can reach the Reticulum configuration.
Validation is authoritative: the Supervisor schema in ``config.yaml`` is only a first layer.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Literal

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
    "peers",
    "transport",
    "log_level",
    "memory_limit_mb",
    "replace_identity",
    "home_assistant_integration",
}
ALLOWED_PEER_KEYS = {"name", "host", "port", "network_name", "passphrase"}


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
class Settings:
    peers: tuple[Peer, ...] = ()
    transport: bool = False
    log_level: LogLevel = "normal"
    memory_limit_mb: int = MEMORY_LIMIT_DEFAULT_MB
    replace_identity: bool = False
    home_assistant_integration: bool = False

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

    if problems:
        raise ValidationError(problems)
    return Settings(
        peers=tuple(peers),
        transport=transport,
        log_level=log_level,
        memory_limit_mb=memory,
        replace_identity=replace_identity,
        home_assistant_integration=integration,
    )
