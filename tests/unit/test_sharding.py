# SPDX-License-Identifier: Apache-2.0
"""CI sharding (tests/conftest.py): every test runs in exactly one shard, and tests that share a
wide fixture are never separated."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.conftest import DEFAULT_SECONDS, assign_shards, parse_shard

REPO = Path(__file__).resolve().parents[2]


def test_shard_option_is_validated():
    assert parse_shard("2/3") == (2, 3)
    for bad in ("0/3", "4/3", "1", "a/b", "1/2/3", "-1/2"):
        with pytest.raises(pytest.UsageError):
            parse_shard(bad)


@given(
    groups=st.lists(st.one_of(st.none(), st.sampled_from(["m1", "m2", "m3"])), max_size=60),
    n=st.integers(min_value=1, max_value=6),
    data=st.data(),
)
def test_every_test_lands_in_one_shard_and_groups_stay_together(groups, n, data):
    ids = [f"t{i}" for i in range(len(groups))]
    weights = {i: data.draw(st.floats(min_value=0, max_value=200)) for i in ids if data.draw(st.booleans())}
    shard = assign_shards(ids, groups, weights, n)
    assert len(shard) == len(ids) and all(0 <= s < n for s in shard)
    for key in {g for g in groups if g is not None}:
        assert len({s for s, g in zip(shard, groups, strict=True) if g == key}) == 1
    assert shard == assign_shards(ids, groups, weights, n)  # deterministic: every runner agrees


def test_heavy_tests_are_spread_before_light_ones():
    ids = ["slow1", "slow2", "slow3", *[f"quick{i}" for i in range(30)]]
    weights = {"slow1": 130.0, "slow2": 60.0, "slow3": 50.0}
    shard = assign_shards(ids, [None] * len(ids), weights, 2)
    load = [0.0, 0.0]
    for i, s in zip(ids, shard, strict=True):
        load[s] += weights.get(i, DEFAULT_SECONDS)
    assert shard[0] != shard[1] and shard[1] == shard[2]  # 130 alone; 60 + 50 together
    assert abs(load[0] - load[1]) < 25


def _collected(*args: str) -> list[str]:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if "::" in line]


def test_shards_of_a_real_suite_partition_it_exactly():
    suite = ("tests/unit", "tests/integration", "-m", "not container")
    whole = _collected(*suite)
    parts = [_collected(*suite, "--shard", f"{k}/3") for k in (1, 2, 3)]
    assert sorted(whole) == sorted(t for part in parts for t in part)  # nothing lost, nothing twice
    # The LXMF module tells one story over a shared node: the restart test checks a contact that an
    # earlier test added, so both must run in the same shard, in their original order.
    lxmf = "tests/integration/test_messaging_lxmf.py::"
    added = lxmf + "test_a_contact_added_in_the_dashboard_can_talk_both_ways"
    restart = lxmf + "test_pending_messages_survive_a_restart_and_the_identity_is_kept"
    [home] = [p for p in parts if added in p]
    assert restart in home and home.index(added) < home.index(restart)
