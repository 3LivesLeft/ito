# SPDX-License-Identifier: Apache-2.0
"""Crash consistency of the whole identity-replacement transaction (PR #2 review, item 1).

A simulated crash is injected before every file write that the replacement performs (primary,
backup, state, kept copy, journal). After each crash MeshBeacon is restarted, either with
'Replace identity' still switched on or with it switched off, and must:

* never end in needs_attention (other than the deliberate "switch it off" message);
* never silently change the node's identity: the identity in use afterwards is either the original
  (the replacement had not been authorised on disk yet) or the one replacement that was authorised;
* never perform a second replacement once one has been authorised and recorded;
* always keep the original identity somewhere on disk.
"""

from __future__ import annotations

import pytest

from meshbeacon import fsutil
from meshbeacon import identity as ident
from meshbeacon.identity import IdentityManager, Outcome
from meshbeacon.paths import Paths


class SimulatedCrash(BaseException):
    """BaseException so that no ``except Exception`` in the code under test can swallow it."""


def fp(path):
    loaded = ident.load(path)
    return ident.fingerprint(loaded) if loaded is not None else None


def kept_copies(paths):
    return {ident.fingerprint(ident.from_bytes(p.read_bytes())) for p in paths.meshbeacon.glob("identity.replaced-*")}


def crash_at(monkeypatch, n):
    """Raise SimulatedCrash at the n-th file write (1-based); return a counter of writes."""
    calls = {"count": 0}
    real_write, real_json = fsutil.atomic_write, fsutil.atomic_write_json

    def guard():
        calls["count"] += 1
        if calls["count"] == n:
            raise SimulatedCrash

    def write(*a, **k):
        guard()
        return real_write(*a, **k)

    def write_json(*a, **k):
        guard()
        return real_json(*a, **k)

    monkeypatch.setattr(fsutil, "atomic_write", write)
    monkeypatch.setattr(fsutil, "atomic_write_json", write_json)
    return calls


def writes_in_clean_replacement(tmp_path, monkeypatch):
    paths = Paths(tmp_path / "count")
    IdentityManager(paths).ensure()
    calls = crash_at(monkeypatch, 10**9)
    IdentityManager(paths).ensure(replace_requested=True)
    monkeypatch.undo()
    return calls["count"]


@pytest.mark.parametrize("option_on_restart", [True, False], ids=["still-on", "switched-off"])
def test_interrupted_replacement_at_every_write(tmp_path, monkeypatch, option_on_restart):
    total = writes_in_clean_replacement(tmp_path, monkeypatch)
    assert total >= 3
    for n in range(1, total + 1):
        paths = Paths(tmp_path / f"case-{n}")
        manager = IdentityManager(paths)
        assert manager.ensure().outcome is Outcome.CREATED
        original = fp(paths.identity)

        crash_at(monkeypatch, n)
        with pytest.raises(SimulatedCrash):
            manager.ensure(replace_requested=True)
        monkeypatch.undo()

        # Restart (possibly more than once) with the option as the user left it.
        first = manager.ensure(replace_requested=option_on_restart)
        assert first.outcome is not Outcome.NEEDS_ATTENTION, (n, first.message)
        after = fp(paths.identity)
        assert after is not None
        assert after == original or first.outcome is Outcome.REPLACED, (n, first.outcome)

        # The replacement is never applied twice.
        again = manager.ensure(replace_requested=option_on_restart)
        if option_on_restart:
            assert again.outcome is Outcome.NEEDS_ATTENTION and "Switch off" in again.message, (n, again)
        else:
            assert again.outcome is Outcome.UNCHANGED, (n, again)
        assert fp(paths.identity) == after, n

        # Switching the option off afterwards changes nothing.
        final = manager.ensure(replace_requested=False)
        assert final.outcome is Outcome.UNCHANGED, (n, final)
        assert fp(paths.identity) == after == fp(paths.identity_backup), n

        # The original identity is never lost.
        assert after == original or original in kept_copies(paths), n


def test_authorised_replacement_is_completed_not_repeated(tmp_path, monkeypatch):
    """Once the new identity has been recorded as authorised, a crash must lead to *that* identity
    being installed on restart, whatever the option says — never a second, different one."""
    total = writes_in_clean_replacement(tmp_path, monkeypatch)
    after_commit = 0
    for option_on_restart in (True, False):
        for n in range(1, total + 1):
            paths = Paths(tmp_path / f"auth-{option_on_restart}-{n}")
            manager = IdentityManager(paths)
            manager.ensure()
            crash_at(monkeypatch, n)
            with pytest.raises(SimulatedCrash):
                manager.ensure(replace_requested=True)
            monkeypatch.undo()
            state = fsutil.read_json(paths.identity_state) or {}
            pending = (state.get("pending_replacement") or {}).get("fingerprint")
            manager.ensure(replace_requested=option_on_restart)
            if pending:
                after_commit += 1
                assert fp(paths.identity) == pending, (option_on_restart, n)
                assert not paths.identity_pending.exists()
    assert after_commit >= 6  # crashes after the commit point were exercised for both settings
