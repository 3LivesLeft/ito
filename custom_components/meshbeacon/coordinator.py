# SPDX-License-Identifier: Apache-2.0
"""Polls MeshBeacon's status every 30 seconds and keeps repair issues in step with it."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import AuthError, MeshBeaconClient, MeshBeaconError, Status
from .const import (
    CONF_TOKEN,
    DOMAIN,
    ISSUE_ATTENTION,
    ISSUE_ISOLATED,
    ISSUE_UNREACHABLE,
    SCAN_INTERVAL,
    UNREACHABLE_GRACE,
)

_LOGGER = logging.getLogger(__name__)

type MeshBeaconConfigEntry = ConfigEntry[MeshBeaconCoordinator]

ISSUES = (ISSUE_ISOLATED, ISSUE_UNREACHABLE, ISSUE_ATTENTION)


class MeshBeaconCoordinator(DataUpdateCoordinator[Status]):
    config_entry: MeshBeaconConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MeshBeaconConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.client = MeshBeaconClient(
            async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_TOKEN]
        )
        self._unreachable_since: datetime | None = None

    async def _async_update_data(self) -> Status:
        try:
            status = await self.client.async_get_status()
        except AuthError as exc:
            # The key changes at every app start; the app's new discovery message updates this
            # entry and reloads it, so there is nothing for the user to do.
            raise UpdateFailed("MeshBeacon has a new key; waiting for Home Assistant to receive it") from exc
        except MeshBeaconError as exc:
            raise UpdateFailed(f"MeshBeacon is not reachable ({exc})") from exc
        self._update_issues(status)
        return status

    def _update_issues(self, status: Status) -> None:
        wanted: dict[str, dict[str, str]] = {}
        if status.state == "needs_attention":
            wanted[ISSUE_ATTENTION] = {"message": status.message or ""}
        elif status.problem == "isolated":
            wanted[ISSUE_ISOLATED] = {}
        if status.state != "needs_attention" and status.problem == "peers_unreachable":
            now = dt_util.utcnow()
            self._unreachable_since = self._unreachable_since or now
            if now - self._unreachable_since >= UNREACHABLE_GRACE:
                wanted[ISSUE_UNREACHABLE] = {}
        else:
            self._unreachable_since = None
        for issue in ISSUES:
            if issue in wanted:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue,
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR if issue == ISSUE_ATTENTION else ir.IssueSeverity.WARNING,
                    translation_key=issue,
                    translation_placeholders=wanted[issue],
                )
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue)

    def clear_issues(self) -> None:
        for issue in ISSUES:
            ir.async_delete_issue(self.hass, DOMAIN, issue)
