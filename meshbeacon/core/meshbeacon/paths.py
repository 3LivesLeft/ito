# SPDX-License-Identifier: Apache-2.0
"""Locations of MeshBeacon and Reticulum files under the app's data directory."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    data: Path

    @classmethod
    def from_env(cls) -> Paths:
        return cls(Path(os.environ.get("MESHBEACON_DATA", "/data")))

    @property
    def options(self) -> Path:
        return Path(os.environ.get("MESHBEACON_OPTIONS", str(self.data / "options.json")))

    @property
    def meshbeacon(self) -> Path:
        return self.data / "meshbeacon"

    @property
    def reticulum(self) -> Path:
        return self.data / "reticulum"

    @property
    def rns_config(self) -> Path:
        return self.reticulum / "config"

    @property
    def storage(self) -> Path:
        return self.reticulum / "storage"

    @property
    def identity(self) -> Path:
        return self.storage / "transport_identity"

    @property
    def identity_dir(self) -> Path:
        """The transport identity's backup, staged replacement, state and archives (ADR 0018).

        Under ``/data/reticulum``, owned by Reticulum's user with the identity itself, so that the
        management core never holds key material. Before ADR 0018 these files were in
        ``/data/meshbeacon``; the root init step moves them here (``LEGACY_IDENTITY_FILES``).
        """
        return self.reticulum / "meshbeacon-identity"

    @property
    def identity_backup(self) -> Path:
        return self.identity_dir / "identity.backup"

    @property
    def identity_pending(self) -> Path:
        return self.identity_dir / "identity.pending"

    @property
    def identity_state(self) -> Path:
        return self.identity_dir / "identity.json"

    @property
    def start_history(self) -> Path:
        return self.meshbeacon / "starts.json"

    @property
    def prepare_result(self) -> Path:
        return self.meshbeacon / "prepare-result.json"

    @property
    def regenerable_dirs(self) -> tuple[Path, ...]:
        return (self.storage / "cache", self.storage / "resources")
