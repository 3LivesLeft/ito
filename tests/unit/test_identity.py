# SPDX-License-Identifier: Apache-2.0
"""Identity corruption and recovery (testing strategy §4.3, roadmap LP-6)."""

import json
import stat

import pytest

from meshbeacon import identity as ident
from meshbeacon.identity import IdentityManager, Outcome
from meshbeacon.paths import Paths


@pytest.fixture
def paths(tmp_path):
    p = Paths(tmp_path)
    return p


def fp_of(path):
    return ident.fingerprint(ident.load(path))


def test_first_start_creates_identity_backup_and_state(paths):
    r = IdentityManager(paths).ensure()
    assert r.outcome is Outcome.CREATED
    assert paths.identity.read_bytes() == paths.identity_backup.read_bytes()
    assert len(paths.identity.read_bytes()) == 64
    for f in (paths.identity, paths.identity_backup, paths.identity_state):
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
    state = json.loads(paths.identity_state.read_text())
    assert state["fingerprint"] == fp_of(paths.identity)


def test_second_start_unchanged(paths):
    m = IdentityManager(paths)
    m.ensure()
    before = paths.identity.read_bytes()
    assert m.ensure().outcome is Outcome.UNCHANGED
    assert paths.identity.read_bytes() == before


@pytest.mark.parametrize("damage", [b"", b"\x00" * 10, b"x" * 63, b"x" * 65, b"\xff" * 64])
def test_damaged_primary_restored_from_backup(paths, damage):
    m = IdentityManager(paths)
    m.ensure()
    original = paths.identity.read_bytes()
    paths.identity.write_bytes(damage)
    r = m.ensure()
    assert r.outcome is Outcome.RESTORED
    assert paths.identity.read_bytes() == original


def test_missing_primary_restored_from_backup(paths):
    m = IdentityManager(paths)
    m.ensure()
    original = paths.identity.read_bytes()
    paths.identity.unlink()
    assert m.ensure().outcome is Outcome.RESTORED
    assert paths.identity.read_bytes() == original


def test_damaged_primary_and_backup_refuses_and_leaves_files(paths):
    m = IdentityManager(paths)
    m.ensure()
    paths.identity.write_bytes(b"x" * 10)
    paths.identity_backup.write_bytes(b"y" * 10)
    r = m.ensure()
    assert r.outcome is Outcome.NEEDS_ATTENTION
    assert paths.identity.read_bytes() == b"x" * 10  # untouched for manual recovery
    assert paths.identity_backup.read_bytes() == b"y" * 10


def test_state_only_without_files_refuses(paths):
    m = IdentityManager(paths)
    m.ensure()
    paths.identity.unlink()
    paths.identity_backup.unlink()
    assert m.ensure().outcome is Outcome.NEEDS_ATTENTION
    assert not paths.identity.exists()


def test_corrupt_primary_without_history_refuses(paths):
    paths.storage.mkdir(parents=True)
    paths.identity.write_bytes(b"junk")
    assert IdentityManager(paths).ensure().outcome is Outcome.NEEDS_ATTENTION


def test_changed_primary_restored_when_backup_matches(paths):
    m = IdentityManager(paths)
    m.ensure()
    original = paths.identity.read_bytes()
    other = IdentityManager(Paths(paths.data / "other"))
    other.ensure()
    paths.identity.write_bytes(other.paths.identity.read_bytes())
    assert m.ensure().outcome is Outcome.RESTORED
    assert paths.identity.read_bytes() == original


def test_fingerprint_mismatch_with_no_matching_copy_refuses(paths):
    m = IdentityManager(paths)
    m.ensure()
    other = IdentityManager(Paths(paths.data / "other"))
    other.ensure()
    swapped = other.paths.identity.read_bytes()
    paths.identity.write_bytes(swapped)
    paths.identity_backup.write_bytes(swapped)
    assert m.ensure().outcome is Outcome.NEEDS_ATTENTION
    assert paths.identity.read_bytes() == swapped  # untouched


def test_backup_refreshed_from_valid_primary(paths):
    m = IdentityManager(paths)
    m.ensure()
    paths.identity_backup.write_bytes(b"bad")
    assert m.ensure().outcome is Outcome.UNCHANGED
    assert paths.identity_backup.read_bytes() == paths.identity.read_bytes()


def test_replace_keeps_old_and_requires_switch_off(paths):
    m = IdentityManager(paths, clock=lambda: 1_700_000_000)
    m.ensure()
    old = paths.identity.read_bytes()
    r = m.ensure(replace_requested=True)
    assert r.outcome is Outcome.REPLACED
    assert paths.identity.read_bytes() != old
    kept = list(paths.identity_dir.glob("identity.replaced-*"))
    assert len(kept) == 1 and kept[0].read_bytes() == old
    assert stat.S_IMODE(kept[0].stat().st_mode) == 0o600
    # Option still on at next app start: refused, nothing replaced again.
    new = paths.identity.read_bytes()
    assert m.ensure(replace_requested=True).outcome is Outcome.NEEDS_ATTENTION
    assert paths.identity.read_bytes() == new
    # A restart of RNS within the same app run does not act on the option.
    assert m.ensure(replace_requested=True, allow_replace=False).outcome is Outcome.UNCHANGED
    # Switched off: normal again.
    assert m.ensure(replace_requested=False).outcome is Outcome.UNCHANGED


def test_messages_never_contain_fingerprint(paths):
    m = IdentityManager(paths)
    results = [m.ensure()]
    fp = fp_of(paths.identity)
    paths.identity.write_bytes(b"x")
    results.append(m.ensure())
    results.append(m.ensure(replace_requested=True))
    results.append(m.ensure(replace_requested=True))
    for r in results:
        assert fp not in r.message
        assert fp_of(paths.identity) not in r.message


def test_stale_temp_files_removed(paths):
    paths.storage.mkdir(parents=True)
    stale = paths.storage / ".mbtmp-transport_identity-1-abcd"
    stale.write_bytes(b"partial")
    IdentityManager(paths).ensure()
    assert not stale.exists()


def test_from_bytes_rejects_wrong_lengths():
    assert ident.from_bytes(b"x" * 10) is None
    assert ident.from_bytes(b"x" * 65) is None
