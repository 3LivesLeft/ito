# SPDX-License-Identifier: Apache-2.0
"""The messaging identity (ADR 0009): separate from the transport identity, validated before every
start (CLAUDE.md rule 13), never logged (rule 5).

``/data/messaging/identity`` and its verified copy ``identity.backup`` (both 0600, owned by the
engine's user). On the first start a new identity is created. A damaged identity is restored from
the backup; if both are damaged, nothing is replaced and the engine does not start, so that manual
recovery stays possible. It shares nothing with the transport identity: replacing either leaves
the other unchanged (MS-2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import fsutil
from ..identity import from_bytes


class IdentityError(Exception):
    """Neither the identity nor its backup is valid: the engine must not start (rule 13)."""


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def load_or_create(folder: Path) -> tuple[Any, str]:
    """(RNS identity, what happened: created | unchanged | restored). Raises IdentityError."""
    import RNS

    fsutil.ensure_dir(folder)
    primary_path, backup_path = folder / "identity", folder / "identity.backup"
    primary_bytes, backup_bytes = _read(primary_path), _read(backup_path)
    primary = from_bytes(primary_bytes) if primary_bytes is not None else None
    backup = from_bytes(backup_bytes) if backup_bytes is not None else None
    if primary is not None and primary_bytes is not None:
        if backup_bytes != primary_bytes:
            fsutil.atomic_write(backup_path, primary_bytes)
        return primary, "unchanged"
    if backup is not None and backup_bytes is not None:
        fsutil.atomic_write(primary_path, backup_bytes)
        return backup, "restored"
    if primary_bytes is not None or backup_bytes is not None:
        raise IdentityError("the messaging identity and its backup are both damaged")
    data = RNS.Identity().get_private_key()
    fsutil.atomic_write(primary_path, data)
    fsutil.atomic_write(backup_path, data)
    created = from_bytes(data)
    if created is None:  # pragma: no cover - RNS returned an identity it cannot load
        raise IdentityError("could not create a messaging identity")
    return created, "created"
