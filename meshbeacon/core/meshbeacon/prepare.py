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
import sys
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
        result.fail("MeshBeacon could not read its options. Open the Configuration tab and save them again.", "options")
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
            "There is less than 200 MB of free storage, so MeshBeacon has not started Reticulum. "
            "Free some space on your Home Assistant device and restart the app.",
            "storage",
        )
        return False
    if free < FREE_SPACE_WARN:
        result.warnings.append("Free storage is below 1 GB. MeshBeacon will stop Reticulum below 200 MB.")
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
    if settings is None or not check_storage(paths, result):
        return result

    manager = IdentityManager(paths)
    outcome = manager.ensure(replace_requested=settings.replace_identity, allow_replace=(mode == "start"))
    result.identity = outcome.outcome.value
    if not outcome.ok:
        return result.fail(outcome.message, "identity")
    if mode == "start" or outcome.outcome is not Outcome.UNCHANGED:
        result.info.append(outcome.message)

    cap_regenerable(paths, result)

    rpc_key = rnsconfig.new_rpc_key()  # messaging off: a fresh key that nobody else holds
    if settings.messaging.enabled:
        # Messaging on: the key the engine is given too (ADR 0023). If it is missing, Reticulum
        # still starts; only messaging is affected, and the dashboard says so.
        shared = rnsconfig.read_shared_rpc_key()
        if shared is None:
            result.info.append(
                "⚠ Messaging's access key for Reticulum is missing, so messaging cannot work. Home "
                "Assistant is probably still using the app's previous security profile: update the "
                "app to the latest version (Rebuild is not enough). Reticulum works normally."
            )
        else:
            rpc_key = shared
    try:
        text = rnsconfig.render(settings, rpc_key, share_instance=settings.messaging.enabled)
    except rnsconfig.RenderError:
        return result.fail(
            "MeshBeacon could not build a safe Reticulum configuration from your options, so it "
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
            f"MeshBeacon hit an unexpected problem while preparing to start ({type(exc).__name__}). "
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
