# SPDX-License-Identifier: Apache-2.0
"""Root test configuration.

The Home Assistant integration tests (tests/ha) need Home Assistant and its test harness, which
require a newer Python than the app image. They run in their own CI job; elsewhere they are not
collected.

Sharding (CI only). ``--shard K/N`` runs shard K (1-based) of N, so CI can spread one suite over N
runners. Shards are cut after every other selection (``-m``, ``-k``, paths), so together the N
shards run exactly the tests that one unsharded run would: each test lands in exactly one shard.
Tests that share a module-, class- or package-scoped fixture may depend on each other's order
(tests/integration/test_messaging_lxmf.py is one story told over a shared node), so all of a
module's tests that use such a fixture stay together, in their order, in one shard. A module whose
wide fixtures hold no state between tests can opt out with ``pytestmark = pytest.mark.shard_per_test``.
Groups are balanced by the run times recorded in ``tests/durations.json`` (longest first, each to
the shard with the least work so far); a test with no recorded time counts as ``DEFAULT_SECONDS``.
A stale table only makes shards less even, never skips a test. Refresh it with
``--store-durations`` after adding or noticeably changing slow tests.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

collect_ignore = [] if importlib.util.find_spec("pytest_homeassistant_custom_component") else ["ha"]

DURATIONS = Path(__file__).with_name("durations.json")
DEFAULT_SECONDS = 0.05
_RECORD_AT_LEAST = 1.0  # shorter tests are left at the default, which keeps the table small
_measured: dict[str, float] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("meshbeacon sharding")
    group.addoption("--shard", default=None, metavar="K/N", help="run only shard K of N (1-based)")
    group.addoption(
        "--store-durations",
        action="store_true",
        help=f"merge this run's test times (>= {_RECORD_AT_LEAST} s) into {DURATIONS.name}",
    )


def parse_shard(value: str) -> tuple[int, int]:
    try:
        k, n = (int(part) for part in value.split("/"))
    except ValueError:
        raise pytest.UsageError(f"--shard must look like K/N, not {value!r}") from None
    if not 1 <= k <= n:
        raise pytest.UsageError(f"--shard {value}: K must be between 1 and N")
    return k, n


def assign_shards(nodeids: list[str], groups: list[str | None], weights: dict[str, float], n: int) -> list[int]:
    """Shard index (0-based) for each node ID. Tests with the same group key share a shard; a test
    whose key is None is a group of its own. Heaviest group first, each to the least-loaded shard."""
    members: dict[object, list[int]] = {}
    for i, key in enumerate(groups):
        members.setdefault(i if key is None else key, []).append(i)
    units = [(sum(weights.get(nodeids[i], DEFAULT_SECONDS) for i in idx), idx) for idx in members.values()]
    units.sort(key=lambda unit: (-unit[0], unit[1][0]))
    load = [0.0] * n
    shard = [0] * len(nodeids)
    for weight, idx in units:
        target = min(range(n), key=lambda s: (load[s], s))
        for i in idx:
            shard[i] = target
        load[target] += weight
    return shard


def _group(item: pytest.Item) -> str | None:
    """The module's node ID if the test uses a fixture wider than a function, else None."""
    if item.get_closest_marker("shard_per_test"):
        return None
    info = getattr(item, "_fixtureinfo", None)
    if info is None:  # unknown item type: keep the whole module together, which is always safe
        return item.nodeid.split("::", 1)[0]
    for defs in info.name2fixturedefs.values():
        if defs and defs[-1].scope in ("class", "module", "package"):
            return item.nodeid.split("::", 1)[0]
    return None


def _load_durations() -> dict[str, float]:
    try:
        data = json.loads(DURATIONS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {str(k): float(v) for k, v in data.items()}


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    value = config.getoption("--shard")
    if value is None:
        return
    k, n = parse_shard(value)
    shard = assign_shards([item.nodeid for item in items], [_group(item) for item in items], _load_durations(), n)
    # Collection order is kept within a shard, so module fixtures are still set up once per module.
    keep = [item for item, s in zip(items, shard, strict=True) if s == k - 1]
    drop = [item for item, s in zip(items, shard, strict=True) if s != k - 1]
    if drop:
        config.hook.pytest_deselected(items=drop)
    items[:] = keep


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    _measured[report.nodeid] = _measured.get(report.nodeid, 0.0) + report.duration


def pytest_sessionfinish(session: pytest.Session) -> None:
    if not session.config.getoption("--store-durations") or not _measured:
        return
    table = _load_durations()
    for nodeid, seconds in _measured.items():
        if seconds >= _RECORD_AT_LEAST:
            table[nodeid] = round(seconds, 1)
        else:
            table.pop(nodeid, None)
    DURATIONS.write_text(json.dumps(dict(sorted(table.items())), indent=1) + "\n", encoding="utf-8")
