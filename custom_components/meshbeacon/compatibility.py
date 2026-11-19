# SPDX-License-Identifier: Apache-2.0
"""Which app versions this integration works with (M1, docs/releasing.md).

The app (Supervisor app store) and the integration (Marketplace) update separately, on different
schedules, so for a while one may be newer than the other. Both carry the same version number.

- Integration N works with app N and with app N−1 (the previous minor release), so either can be
  updated first in the common case.
- An app newer than the integration may offer what the integration does not understand: repair
  "update the integration".
- An app more than one minor release older (or of another major version): repair "update the app".

The status schema (``SCHEMA_VERSION``) remains the hard compatibility check; this only explains a
mismatch in plain words before anything breaks. Unparseable versions raise no repair.
"""

from __future__ import annotations

import re
from typing import Final

ISSUE_APP_OUTDATED: Final = "app_outdated"
ISSUE_INTEGRATION_OUTDATED: Final = "integration_outdated"
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _parse(version: str | None) -> tuple[int, int, int] | None:
    match = _VERSION.match(version or "")
    return None if match is None else (int(match[1]), int(match[2]), int(match[3]))


def mismatch(app_version: str | None, integration_version: str | None) -> str | None:
    """The repair to raise, or None when the two work together."""
    app, integration = _parse(app_version), _parse(integration_version)
    if app is None or integration is None:
        return None
    if app[0] != integration[0]:
        return ISSUE_INTEGRATION_OUTDATED if app[0] > integration[0] else ISSUE_APP_OUTDATED
    if app[1] > integration[1]:
        return ISSUE_INTEGRATION_OUTDATED
    if app[1] < integration[1] - 1:
        return ISSUE_APP_OUTDATED
    return None
