# SPDX-License-Identifier: Apache-2.0
"""Pre-start preparation, run as a short-lived process before every RNS start.

Steps: validate options → storage checks → identity validation/recovery → render the RNS
configuration → repair permissions. The outcome is written as JSON to ``--result``; problems that
a restart cannot fix are reported as ``needs_attention`` rather than raised, so that the caller
never enters a restart loop.

This process imports RNS (for the identity API and the configuration parser) and exits, so the
long-running supervisor does not carry RNS's memory footprint.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import fsutil, rnsconfig
from .identity import IdentityManager, Outcome
from .paths import Paths
from .settings import Settings, ValidationError, parse_options

FREE_SPACE_FLOOR = 200 * 1024 * 1024
FREE_SPACE_WARN = 1024 * 1024 * 1024
REGENERABLE_CAP = 100 * 1024 * 1024


@dataclass
class PrepareResult:
    ok: bool = True
    attention: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    identity: str = ""
    # Stable code for the first problem (v0.2 diagnostics): options, storage, identity,
    # configuration or unexpected.
    problem: str = ""

    def fail(self, message: str, problem: str) -> PrepareResult:
        self.ok = False
        self.problem = self.problem or problem
        self.attention.append(message)
        return self


def load_settings(paths: Paths, result: PrepareResult) -> Settings | None:
    try:
        raw = json.loads(paths.options.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    except (OSError, ValueError):
        result.fail("ito could not read its options. Open the Configuration tab and save them again.", "options")
        return None
    try:
        return parse_options(raw)
    except ValidationError as exc:
        result.ok = False
        result.problem = result.problem or "options"
        result.attention.append("Some options need correcting in the Configuration tab:")
        result.attention.extend(f"  • {p}" for p in exc.problems)
        return None


def check_storage(paths: Paths, result: PrepareResult) -> bool:
    free = shutil.disk_usage(paths.data).free
    if free < FREE_SPACE_FLOOR:
        result.fail(
            "There is less than 200 MB of free storage, so ito has not started Reticulum. "
            "Free some space on your Home Assistant device and restart the app.",
            "storage",
        )
        return False
    if free < FREE_SPACE_WARN:
        result.warnings.append("Free storage is below 1 GB. ito will stop Reticulum below 200 MB.")
    return True


def check_sqlite_storage(paths: Paths, result: PrepareResult) -> bool:
    """Exercise SQLite's persistent and temporary storage without touching RNS databases."""
    try:
        # RNS uses SQLite both for destination persistence and temporary announce tables.
        # A successful directory check alone does not prove either operation works.
        with tempfile.TemporaryDirectory(prefix=".sqlite-check-", dir=paths.storage) as folder:
            db = Path(folder) / "check.db"
            with sqlite3.connect(db) as conn:
                conn.execute("PRAGMA temp_store=FILE")
                conn.execute("CREATE TABLE check_data (value INTEGER)")
                conn.execute("INSERT INTO check_data VALUES (1)")
                conn.execute("CREATE TEMP TABLE check_temp (value INTEGER)")
                conn.execute("INSERT INTO check_temp VALUES (1)")
                conn.commit()
            with sqlite3.connect(db) as conn:
                if conn.execute("SELECT value FROM check_data").fetchone() != (1,):
                    raise sqlite3.DatabaseError("SQLite persistence verification failed")
        # Check the OS temporary directory too: SQLite can use it for temporary files.
        with tempfile.TemporaryFile(dir=tempfile.gettempdir()) as temporary:
            temporary.write(b"sqlite-temp-check")
            temporary.flush()
    except (OSError, sqlite3.Error) as exc:
        result.fail(
            "Reticulum's database storage is not writable or SQLite cannot use its temporary "
            f"directory ({type(exc).__name__}). Check the app's storage permissions and free "
            "space; existing identities and databases have not been modified.",
            "storage",
        )
        return False
    return True


def cap_regenerable(paths: Paths, result: PrepareResult) -> None:
    total = sum(fsutil.tree_size(d) for d in paths.regenerable_dirs)
    if total > REGENERABLE_CAP:
        for directory in paths.regenerable_dirs:
            fsutil.clear_directory(directory)
        result.info.append("Cleared Reticulum's temporary cache because it had grown above 100 MB.")


def prepare(paths: Paths, *, mode: str) -> PrepareResult:
    result = PrepareResult()
    # Reticulum's own folders only: since ADR 0018 the prepare step runs as Reticulum's user and
    # cannot (and need not) reach the core's /data/meshbeacon.
    for directory in (paths.reticulum, paths.storage, paths.identity_dir):
        fsutil.ensure_dir(directory)

    settings = load_settings(paths, result)
    if settings is None or not check_storage(paths, result) or not check_sqlite_storage(paths, result):
        return result

    manager = IdentityManager(paths)
    outcome = manager.ensure(replace_requested=settings.replace_identity, allow_replace=(mode == "start"))
    result.identity = outcome.outcome.value
    if not outcome.ok:
        return result.fail(outcome.message, "identity")
    if mode == "start" or outcome.outcome is not Outcome.UNCHANGED:
        result.info.append(outcome.message)

    cap_regenerable(paths, result)

    rpc_key = rnsconfig.new_rpc_key()  # no optional service: a fresh key that nobody else holds
    if settings.share_instance:
        # Messaging or pages on: the key their services are given too (ADR 0023, ADR 0027). If it
        # is missing, Reticulum still starts; only those services are affected, and the dashboard
        # says so.
        shared = rnsconfig.read_shared_rpc_key()
        if shared is None:
            result.info.append(
                "⚠ The access key for Reticulum is missing, so messaging and pages cannot work. Home "
                "Assistant is probably still using the app's previous security profile: update the "
                "app to the latest version (Rebuild is not enough). Reticulum works normally."
            )
        else:
            rpc_key = shared
    try:
        text = rnsconfig.render(settings, rpc_key, share_instance=settings.share_instance)
    except rnsconfig.RenderError:
        return result.fail(
            "ito could not build a safe Reticulum configuration from your options, so it "
            "has not started Reticulum. Check the peer details in the Configuration tab.",
            "configuration",
        )
    fsutil.atomic_write(paths.rns_config, text.encode())
    fsutil.repair_permissions(paths.reticulum)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meshbeacon-prepare")
    parser.add_argument("--mode", choices=("start", "restart"), required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--result", type=Path, help="write the result to this file (started by the core)")
    target.add_argument("--result-fd", type=int, help="write the result to this descriptor (s6 service, ADR 0018)")
    args = parser.parse_args(argv)
    paths = Paths.from_env()
    try:
        result = prepare(paths, mode=args.mode)
    except Exception as exc:  # unexpected: report, never loop
        result = PrepareResult().fail(
            f"ito hit an unexpected problem while preparing to start ({type(exc).__name__}). "
            "It has not started Reticulum. Restart the app; if this repeats, please report it.",
            "unexpected",
        )
    if args.result_fd is not None:
        with os.fdopen(args.result_fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(result)) + "\n")
    else:
        fsutil.atomic_write_json(args.result, asdict(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
