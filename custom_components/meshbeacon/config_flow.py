# SPDX-License-Identifier: Apache-2.0
"""Set-up through Supervisor discovery only: the app's key is never shown to or typed by anyone."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .client import MeshBeaconClient, MeshBeaconError
from .const import CONF_TOKEN, DOMAIN

_HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def _validate(config: Any) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    host, port, token = config.get("host"), config.get("port"), config.get("token")
    if not isinstance(host, str) or not _HOST.match(host):
        return None
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        return None
    if not isinstance(token, str) or not _TOKEN.match(token):
        return None
    return {CONF_HOST: host, CONF_PORT: port, CONF_TOKEN: token}


class MeshBeaconConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        data = _validate(discovery_info.config)
        if data is None:
            return self.async_abort(reason="invalid_discovery")
        await self.async_set_unique_id(discovery_info.slug)
        # Every app start brings a new key: update the existing entry and reload it.
        self._abort_if_unique_id_configured(updates=data)
        self._discovered = data
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = MeshBeaconClient(
                async_get_clientsession(self.hass),
                self._discovered[CONF_HOST],
                self._discovered[CONF_PORT],
                self._discovered[CONF_TOKEN],
            )
            try:
                await client.async_get_status()
            except MeshBeaconError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="MeshBeacon", data=self._discovered)
        return self.async_show_form(step_id="hassio_confirm", errors=errors)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason="discovery_only")
