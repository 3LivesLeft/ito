# SPDX-License-Identifier: Apache-2.0
"""Crash-safe identity creation, validation and recovery (architecture §4.6).

RNS silently replaces a corrupt identity file with a new key (verified with RNS 1.6.0), so
MeshBeacon creates the identity itself, validates it before **every** RNS start, keeps a verified
backup copy and never lets RNS start without a valid identity in place.

Identity fingerprints (public hashes) are stored only in ``identity.json`` (0600) and are never
returned in messages or written to logs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from . import fsutil
from .paths import Paths

IDENTITY_SIZE = 64  # RNS private key file: 32-byte X25519 key + 32-byte Ed25519 key


class Outcome(StrEnum):
    CREATED = "created"
    UNCHANGED = "unchanged"
    RESTORED = "restored"
    REPLACED = "replaced"
    NEEDS_ATTENTION = "needs_attention"


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    message: str

    @property
    def ok(self) -> bool:
        return self.outcome is not Outcome.NEEDS_ATTENTION


MSG_DAMAGED_NO_BACKUP = (
    "Your node's identity file is damaged or missing, and no valid backup copy was found. "
    "MeshBeacon has NOT created a new one, because that would change your node's address. "
    "Restore the app from a Home Assistant backup, or, to start with a new identity, turn on "
    "'Replace identity' and restart the app."
)
MSG_MISMATCH = (
    "Your node's identity is not the one MeshBeacon used last time, so MeshBeacon has stopped to "
    "protect it. If you restored only some files, restore the whole app from a Home Assistant "
    "backup. To start with a new identity, turn on 'Replace identity' and restart the app."
)
MSG_RESTORED = (
    "Node identity: the identity file was damaged or missing and has been restored from "
    "MeshBeacon's verified backup copy. Your node's address is unchanged."
)
MSG_RESTORED_CHANGED = (
    "Node identity: the identity file had changed unexpectedly (it may have been damaged) and has "
    "been restored from MeshBeacon's verified backup copy. Your node's address is unchanged."
)
MSG_SWITCH_OFF = (
    "Your node's identity has already been replaced. Switch off 'Replace identity' in the "
    "Configuration tab and restart the app. MeshBeacon will not replace it again automatically."
)


def _rns() -> Any:
    import RNS

    return RNS


def load(path: Path) -> Any | None:
    """Return an RNS Identity loaded from ``path`` using the public API, or None if invalid."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return from_bytes(data)


def from_bytes(data: bytes) -> Any | None:
    if len(data) != IDENTITY_SIZE:
        return None
    try:
        identity = _rns().Identity.from_bytes(data)
    except Exception:
        return None
    if identity is None or identity.get_private_key() != data:
        return None
    return identity


def fingerprint(identity: Any) -> str:
    return str(identity.hash.hex())


def _new_identity_bytes() -> bytes:
    data = bytes(_rns().Identity().get_private_key())
    if from_bytes(data) is None:  # pragma: no cover - would indicate a broken RNS installation
        raise RuntimeError("RNS produced an identity that does not load")
    return data


class IdentityManager:
    def __init__(self, paths: Paths, clock: Any = time.time) -> None:
        self.paths = paths
        self.clock = clock

    # -- state -------------------------------------------------------------------------------
    def _state(self) -> dict[str, Any]:
        value = fsutil.read_json(self.paths.identity_state)
        return value if isinstance(value, dict) else {}

    def _save_state(self, state: dict[str, Any]) -> None:
        fsutil.atomic_write_json(self.paths.identity_state, state)

    # -- operations --------------------------------------------------------------------------
    def _install(self, data: bytes, state: dict[str, Any]) -> None:
        """Write primary, then backup, then state — each atomically, in that order."""
        identity = from_bytes(data)
        if identity is None:
            raise RuntimeError("refusing to install an identity that does not load")
        fsutil.atomic_write(self.paths.identity, data)
        fsutil.atomic_write(self.paths.identity_backup, data)
        state["fingerprint"] = fingerprint(identity)
        self._save_state(state)

    def _keep_replaced(self, data: bytes) -> None:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(self.clock()))
        target = self.paths.meshbeacon / f"identity.replaced-{stamp}"
        suffix = 0
        while target.exists():
            suffix += 1
            target = self.paths.meshbeacon / f"identity.replaced-{stamp}-{suffix}"
        fsutil.atomic_write(target, data)

    def ensure(self, *, replace_requested: bool = False, allow_replace: bool = True) -> Result:
        """Make sure a valid identity is in place before RNS starts.

        ``allow_replace`` is False for the validation that runs before an RNS *restart* within the
        same app run, so that the replace option is acted on only once per app start.
        """
        for directory in (self.paths.storage, self.paths.meshbeacon):
            fsutil.ensure_dir(directory)
            fsutil.remove_stale_temp_files(directory)

        state = self._state()
        recorded = state.get("fingerprint")

        if allow_replace:
            if replace_requested:
                if state.get("replace_applied"):
                    return Result(Outcome.NEEDS_ATTENTION, MSG_SWITCH_OFF)
                return self._replace(state)
            if state.get("replace_applied"):
                state["replace_applied"] = False
                self._save_state(state)

        primary_bytes = _read(self.paths.identity)
        primary = from_bytes(primary_bytes) if primary_bytes is not None else None
        backup_bytes = _read(self.paths.identity_backup)
        backup = from_bytes(backup_bytes) if backup_bytes is not None else None

        backup_fp = fingerprint(backup) if backup is not None else None

        if primary is not None:
            fp = fingerprint(primary)
            if not recorded or fp == recorded:
                if primary_bytes is not None and backup_bytes != primary_bytes:
                    fsutil.atomic_write(self.paths.identity_backup, primary_bytes)
                if not recorded:
                    state["fingerprint"] = fp
                    self._save_state(state)
                return Result(Outcome.UNCHANGED, "Node identity: unchanged since last start.")
            # The primary loads but is not the recorded identity: same-length corruption (any 64
            # bytes form a valid key pair) or a swapped file. Prefer the verified backup.
            if backup_bytes is not None and backup_fp == recorded:
                fsutil.atomic_write(self.paths.identity, backup_bytes)
                return Result(Outcome.RESTORED, MSG_RESTORED_CHANGED)
            return Result(Outcome.NEEDS_ATTENTION, MSG_MISMATCH)

        if backup is not None and backup_bytes is not None:
            if recorded and backup_fp != recorded:
                return Result(Outcome.NEEDS_ATTENTION, MSG_MISMATCH)
            fsutil.atomic_write(self.paths.identity, backup_bytes)
            if not recorded and backup_fp is not None:
                state["fingerprint"] = backup_fp
                self._save_state(state)
            return Result(Outcome.RESTORED, MSG_RESTORED)

        prior_identity_existed = bool(recorded) or primary_bytes is not None or backup_bytes is not None
        if prior_identity_existed:
            # Leave every file untouched so that manual recovery remains possible.
            return Result(Outcome.NEEDS_ATTENTION, MSG_DAMAGED_NO_BACKUP)

        self._install(_new_identity_bytes(), state)
        return Result(Outcome.CREATED, "Node identity: created a new identity for this node.")

    def _replace(self, state: dict[str, Any]) -> Result:
        old = _read(self.paths.identity)
        if old:
            self._keep_replaced(old)
        state["replace_applied"] = True
        self._install(_new_identity_bytes(), state)
        return Result(
            Outcome.REPLACED,
            "Node identity: replaced as you asked. The previous identity has been kept in the "
            "app's data folder. Switch off 'Replace identity' before the next restart.",
        )


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return b""  # unreadable counts as damaged, never as absent
