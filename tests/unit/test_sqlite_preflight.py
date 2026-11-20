# SPDX-License-Identifier: Apache-2.0
"""SQLite preflight regression tests (no existing RNS database is opened)."""

from pathlib import Path

from meshbeacon.paths import Paths
from meshbeacon.prepare import PrepareResult, check_sqlite_storage


def test_sqlite_preflight_succeeds_and_preserves_existing_files(tmp_path: Path) -> None:
    paths = Paths(tmp_path)
    paths.storage.mkdir(parents=True)
    identity = paths.identity
    identity.write_bytes(b"existing-identity")
    result = PrepareResult()
    assert check_sqlite_storage(paths, result)
    assert result.ok
    assert identity.read_bytes() == b"existing-identity"
    assert sorted(p.name for p in paths.storage.iterdir()) == ["transport_identity"]


def test_sqlite_preflight_reports_missing_storage(tmp_path: Path) -> None:
    result = PrepareResult()
    assert not check_sqlite_storage(Paths(tmp_path), result)
    assert result.problem == "storage"
    assert not result.ok
    assert "database storage" in result.attention[0]
