# SPDX-License-Identifier: Apache-2.0
"""Polls MeshBeacon's status every 60 seconds and keeps repair issues in step with it."""

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
from .compatibility import ISSUE_APP_OUTDATED, ISSUE_INTEGRATION_OUTDATED, mismatch
from .config_flow import validate_discovery
from .const import (
    CONF_CERT,
    CONF_TOKEN,
    DOMAIN,
    ISSUE_ATTENTION,
    ISSUE_ISOLATED,
    ISSUE_UNREACHABLE,
    REFRESH_INTERVAL,
    SCAN_INTERVAL,
    UNREACHABLE_GRACE,
)
from .conversations import MessagingHub, remember_key
from .nodes import app_slug

_LOGGER = logging.getLogger(__name__)

type MeshBeaconConfigEntry = ConfigEntry[MeshBeaconCoordinator]

# Where the user finds the update. Version mismatches link to the update guide.
LEARN_MORE = {
    ISSUE_APP_OUTDATED: "https://github.com/3LivesLeft/ito/blob/main/docs/getting-started.md#updating",
    ISSUE_INTEGRATION_OUTDATED: "https://github.com/3LivesLeft/ito/blob/main/docs/getting-started.md#updating",
}
ISSUES = (ISSUE_ISOLATED, ISSUE_UNREACHABLE, ISSUE_ATTENTION, ISSUE_APP_OUTDATED, ISSUE_INTEGRATION_OUTDATED)


class MeshBeaconCoordinator(DataUpdateCoordinator[Status]):
    config_entry: MeshBeaconConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MeshBeaconConfigEntry, integration_version: str | None = None
    ) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.client = MeshBeaconClient(
            async_get_clientsession(hass),
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            entry.data[CONF_TOKEN],
            entry.data[CONF_CERT],
        )
        self._unreachable_since: datetime | None = None
        self._last_refresh: datetime | None = None
        self.integration_version = integration_version
        self.messaging = MessagingHub(hass, entry)
        self._messaging_state: str | None = None

    async def _async_update_data(self) -> Status:
        try:
            status = await self.client.async_get_status()
        except AuthError as exc:
            # The key changes at every app start. Normally the app's new discovery message updates
            # this entry and reloads it. If that push was missed, read the app's current message
            # from the Supervisor ourselves, so that nobody has to do anything.
            if await self._async_refresh_token():
                try:
                    status = await self.client.async_get_status()
                except MeshBeaconError as retry_exc:
                    raise UpdateFailed(f"ito is not reachable ({type(retry_exc).__name__})") from retry_exc
                self._update_issues(status)
                self._messaging_changed(status)
                return status
            raise UpdateFailed("ito has a new key; waiting for Home Assistant to receive it") from exc
        except MeshBeaconError as exc:
            raise UpdateFailed(f"ito is not reachable ({type(exc).__name__}: {exc})") from exc
        self._update_issues(status)
        self._messaging_changed(status)
        return status

    def _messaging_changed(self, status: Status) -> None:
        """Tell an open Messages view when messaging stops, starts or recovers."""
        state = status.messaging.state if status.messaging is not None else None
        if state != self._messaging_state:
            self._messaging_state = state
            self.messaging.notify({"type": "changed"})

    async def _async_refresh_token(self) -> bool:
        """Fetch this app's discovery message from the Supervisor; True if it held a new key.

        Only the message sent by the app this entry belongs to (matched by slug, which the
        Supervisor sets) is used, and it passes the same checks as the config flow. At most one
        attempt per five minutes.
        """
        now = dt_util.utcnow()
        if self._last_refresh is not None and now - self._last_refresh < REFRESH_INTERVAL:
            return False
        self._last_refresh = now
        slug = app_slug(self.config_entry)
        try:
            from homeassistant.components.hassio import get_supervisor_client  # noqa: PLC0415 - optional

            messages = await get_supervisor_client(self.hass).discovery.list()
        except Exception:  # not supervised, Supervisor unavailable, or an API change
            return False
        for message in messages:
            if message.addon != slug or message.service != DOMAIN:
                continue
            data = validate_discovery(slug, message.config)
            if data is not None:
                remember_key(self.hass, slug, message.config)  # memory only (ADR 0024)
            if data is None or (
                data[CONF_TOKEN] == self.config_entry.data.get(CONF_TOKEN)
                and data[CONF_CERT] == self.config_entry.data.get(CONF_CERT)
            ):
                return False
            self.hass.config_entries.async_update_entry(self.config_entry, data={**self.config_entry.data, **data})
            self.client = MeshBeaconClient(
                async_get_clientsession(self.hass), data[CONF_HOST], data[CONF_PORT], data[CONF_TOKEN], data[CONF_CERT]
            )
            return True
        return False

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
        # The app and the integration update separately (compatibility.py).
        if version_issue := mismatch(status.version, self.integration_version):
            wanted[version_issue] = {
                "app_version": status.version or "",
                "integration_version": self.integration_version or "",
            }
        for issue in ISSUES:
            if issue in wanted:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue,
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR if issue == ISSUE_ATTENTION else ir.IssueSeverity.WARNING,
                    learn_more_url=LEARN_MORE.get(issue),
                    translation_key=issue,
                    translation_placeholders=wanted[issue],
                )
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue)

    def clear_issues(self) -> None:
        for issue in ISSUES:
            ir.async_delete_issue(self.hass, DOMAIN, issue)
