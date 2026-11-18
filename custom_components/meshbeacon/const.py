# SPDX-License-Identifier: Apache-2.0
"""Constants for the MeshBeacon integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "meshbeacon"
MANUFACTURER: Final = "MeshBeacon"
# 60 s matches the app's 60 s rate window and keeps recorder growth small (v0.2 review).
SCAN_INTERVAL: Final = timedelta(seconds=60)
REQUEST_TIMEOUT: Final = 10
SCHEMA_VERSION: Final = 1

CONF_TOKEN: Final = "token"  # noqa: S105 - the option key, not a secret

# Keep in step with meshbeacon/core/meshbeacon/supervisor.py (a test checks this).
STATES: Final = ("starting", "running", "restarting", "needs_attention")
CONNECTIVITY: Final = ("isolated", "offline", "partial", "online", "unknown")
PROBLEMS: Final = (
    "none",
    "isolated",
    "peers_unreachable",
    "some_peers_unreachable",
    "reticulum_restarting",
    "reticulum_failing",
    "restart_loop_paused",
    "options",
    "storage",
    "identity",
    "configuration",
    "data_folder",
    "preparation_failed",
    "unexpected",
)

# Repair issues and the problem codes that raise them.
ISSUE_ISOLATED: Final = "isolated"
ISSUE_UNREACHABLE: Final = "peers_unreachable"
ISSUE_ATTENTION: Final = "needs_attention"
UNREACHABLE_GRACE: Final = timedelta(minutes=10)  # short outages do not raise a repair issue
REFRESH_INTERVAL: Final = timedelta(minutes=5)  # at most one key refresh from the Supervisor
