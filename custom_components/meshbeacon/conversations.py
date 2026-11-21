# SPDX-License-Identifier: Apache-2.0
"""LXMF messaging in Home Assistant (M5, ADR 0024): the panel's Messages view.

Path, and who checks what at each step:

1. **Browser → Home Assistant.** Websocket commands ``meshbeacon/messaging/*``, for
   **administrators only** (``require_admin``), on Home Assistant's own authenticated connection.
   The browser never sees a key: only conversations, as the view needs them.
2. **Home Assistant → app.** ``POST /api/v1/messaging`` on the app's pinned-TLS listener, with the
   app's **messaging key**. The key arrives in the app's discovery message and is held **in memory
   only** (``hass.data``), never in the config entry, ``.storage``, backups, logs or diagnostics;
   after a restart of Home Assistant it is read again from the Supervisor's discovery store.
3. **App core → engine.** The core passes only the conversation view's operations on, with rate
   limits; the engine validates everything again.

Nothing here creates an entity or fires a bus event, so no message text or address reaches the
recorder, the logbook or the event history (MS-7). Message text is never logged.

Live updates: while a panel is subscribed, one long poll per app (``wait``, 8 s) tells the panel
when anything changed; it then reads what it shows. Nobody subscribed: no requests at all. Only a
command that changes something is announced to the panels: a read never is, because the panel
answers every announcement with reads (announcing reads made an endless request loop).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import Callable
from typing import Any

import aiohttp
import probatio
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import async_response, require_admin, websocket_command
from homeassistant.components.websocket_api.messages import event_message
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .client import read_bounded
from .const import CONF_CERT, DOMAIN
from .nodes import app_slug

_LOGGER = logging.getLogger(__name__)

PATH = "/api/v1/messaging"
KEYS = f"{DOMAIN}_messaging_keys"  # hass.data: app slug -> messaging key (memory only)
KEY = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
CONF_MESSAGING_KEY = "messaging_key"
MAX_RESPONSE = 4 * 1024 * 1024  # a page of 50 messages of 8 KiB, however JSON escapes them
TIMEOUT = 15.0
WAIT = 8.0  # the app allows at most 8 s
MIN_INTERVAL = 1.0
KEY_REFRESH_EVERY = 30.0
BACKOFF = (5.0, 15.0, 30.0, 60.0)
MAX_TEXT_BYTES = 8192
CONTACT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MESSAGE_ID = re.compile(r"^[0-9a-f]{32}$")
IDEMPOTENCY = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
WS_PREFIX = f"{DOMAIN}/messaging"
# Commands that change what the conversation view shows: announced to every subscribed panel.
# Never "conversations" or "history": the panel reads on every announcement (no feedback loop).
CHANGES = frozenset({"send", "retry", "read", "clear", "contact_add", "contact_rename", "contact_remove"})
LOG_EVERY = 60.0  # at most one log line a minute for repeated refusals of the same kind


class MessagingError(Exception):
    """A request that did not succeed. ``code`` is a safe, plain code for the panel."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def remember_key(hass: HomeAssistant, slug: str | None, config: Any) -> None:
    """Keep the messaging key from a validated discovery message, in memory only; forget it when
    the message has none (messaging was switched off)."""
    if not slug:
        return
    keys: dict[str, str] = hass.data.setdefault(KEYS, {})
    key = config.get(CONF_MESSAGING_KEY) if isinstance(config, dict) else None
    if isinstance(key, str) and KEY.match(key):
        keys[slug] = key
    else:
        keys.pop(slug, None)


async def async_discovery_config(hass: HomeAssistant, slug: str | None) -> dict[str, Any] | None:
    """This app's current discovery message, read from the Supervisor (only Core can read it)."""
    if not slug:
        return None
    try:
        from homeassistant.components.hassio import get_supervisor_client  # noqa: PLC0415 - optional

        messages = await get_supervisor_client(hass).discovery.list()
    except Exception:  # not supervised, Supervisor unavailable, or an API change
        return None
    for message in messages:
        if message.addon == slug and message.service == DOMAIN and isinstance(message.config, dict):
            return dict(message.config)
    return None


class MessagingHub:
    """One app's messaging connection: requests, the key, and the live-update long poll."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        self.hass = hass
        self.entry = entry
        self.slug = app_slug(entry)
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._task: asyncio.Task[None] | None = None
        self._key_checked: float | None = None
        self.available: bool | None = None
        self._logged: dict[str, float] = {}  # refusal kind -> when it was last logged

    # -- the key ------------------------------------------------------------------------------
    @property
    def key(self) -> str | None:
        return self.hass.data.get(KEYS, {}).get(self.slug) if self.slug else None

    async def _refresh_key(self) -> bool:
        """Read the key from the Supervisor again (after a restart of HA, or a refused key)."""
        now = dt_util.utcnow().timestamp()
        if self._key_checked is not None and now - self._key_checked < KEY_REFRESH_EVERY:
            return False
        self._key_checked = now
        from .config_flow import validate_discovery  # noqa: PLC0415 - avoids an import cycle

        before = self.key
        config = await async_discovery_config(self.hass, self.slug)
        if config is None or validate_discovery(self.slug, config) is None:
            return False
        remember_key(self.hass, self.slug, config)
        return self.key is not None and self.key != before

    # -- diagnostics (codes and counts only: never content, addresses, contacts or keys) ----------
    def _log_refusal(self, kind: str, code: str) -> None:
        now = dt_util.utcnow().timestamp()
        key = f"{kind}:{code}"
        last = self._logged.get(key)
        if last is not None and now - last < LOG_EVERY:
            return
        self._logged[key] = now
        _LOGGER.warning(
            "Messaging: the app refused %s requests (%s); %d dashboard(s) subscribed. Logged at most once a minute",
            "send" if kind == "send" else "read and other",
            code,
            len(self._listeners),
        )

    def _set_available(self, available: bool, code: str | None = None) -> None:
        if available == self.available:
            return
        if not available:
            _LOGGER.warning("Messaging: live updates from the app stopped (%s); retrying with back-off", code)
        elif self.available is False:
            _LOGGER.info("Messaging: live updates from the app are back")
        self.available = available

    # -- requests -----------------------------------------------------------------------------
    async def request(self, payload: dict[str, Any], *, timeout: float = TIMEOUT) -> dict[str, Any]:
        if self.key is None:
            await self._refresh_key()
        if self.key is None:
            raise MessagingError("not_enabled")
        try:
            return await self._post(payload, timeout)
        except MessagingError as exc:
            if exc.code != "unauthorised" or not await self._refresh_key():
                raise
        return await self._post(payload, timeout)

    async def _post(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        data = self.entry.data
        url = f"https://{data[CONF_HOST]}:{int(data[CONF_PORT])}{PATH}"
        try:
            async with async_get_clientsession(self.hass).post(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode(),  # UTF-8, not \u escapes
                headers={
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=False,
                ssl=aiohttp.Fingerprint(bytes.fromhex(data[CONF_CERT])),  # pinned, as for status
            ) as response:
                if response.status == 401:
                    raise MessagingError("unauthorised")
                if response.status == 404:
                    raise MessagingError("not_enabled")  # the app has messaging off
                body = await read_bounded(response.content, MAX_RESPONSE)
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise MessagingError("unreachable") from exc
        try:
            answer = json.loads(body)
        except ValueError as exc:
            raise MessagingError("internal") from exc
        if not isinstance(answer, dict):
            raise MessagingError("internal")
        if answer.get("ok") is not True:
            error = answer.get("error")
            safe = isinstance(error, str) and re.fullmatch(r"[a-z_]{1,32}", error)
            raise MessagingError(error if safe and isinstance(error, str) else "internal")
        return answer

    # -- live updates ---------------------------------------------------------------------------
    @callback
    def subscribe(self, listener: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        if self._task is None or self._task.done():
            self._task = self.entry.async_create_background_task(self.hass, self._watch(), f"{DOMAIN} messaging")

        @callback
        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)
            if not self._listeners and self._task is not None:
                self._task.cancel()
                self._task = None

        return unsubscribe

    @callback
    def notify(self, event: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            listener(event)

    async def _watch(self) -> None:
        revision = -1
        failures = 0
        while self._listeners:
            started = asyncio.get_running_loop().time()
            try:
                answer = await self.request({"op": "wait", "revision": revision, "wait": WAIT}, timeout=WAIT + 7)
            except MessagingError as exc:
                if self.available is not False:
                    self._set_available(False, exc.code)
                    self.notify({"type": "unavailable", "error": exc.code})
                await asyncio.sleep(BACKOFF[min(failures, len(BACKOFF) - 1)])
                failures += 1
                continue
            failures = 0
            new = answer.get("revision")
            if self.available is not True or (isinstance(new, int) and new != revision):
                self._set_available(True)
                self.notify({"type": "changed"})
            revision = new if isinstance(new, int) else -1
            # Never faster than once a second, whatever the app answers (no busy loop).
            await asyncio.sleep(max(0.0, MIN_INTERVAL - (asyncio.get_running_loop().time() - started)))

    def close(self) -> None:
        self._listeners.clear()
        if self._task is not None:
            self._task.cancel()
            self._task = None


# -- websocket commands (administrators only) ----------------------------------------------------


def _hub(hass: HomeAssistant, entry_id: Any) -> MessagingHub:
    entry = hass.config_entries.async_get_entry(entry_id) if isinstance(entry_id, str) else None
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise MessagingError("not_found")
    hub = getattr(entry.runtime_data, "messaging", None)
    if not isinstance(hub, MessagingHub):
        raise MessagingError("not_found")
    return hub


def _contact(value: Any) -> str:
    if not isinstance(value, str) or not CONTACT.match(value):
        raise MessagingError("unknown_contact")
    return value


def _short(value: Any, limit: int, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8", "surrogatepass")) > limit:
        raise MessagingError(code)
    return value


def build_request(kind: str, msg: dict[str, Any]) -> dict[str, Any]:
    """The app request for a panel command. Validated here first; the app validates again."""
    if kind == "conversations":
        return {"op": "conversations"}
    if kind == "history":
        request: dict[str, Any] = {"op": "history", "contact": _contact(msg.get("contact")), "limit": 50}
        before = msg.get("before")
        if before is not None:
            if isinstance(before, bool) or not isinstance(before, int) or before < 1:
                raise MessagingError("invalid")
            request["before"] = before
        return request
    if kind in ("read", "clear", "contact_remove"):
        return {"op": kind, "contact": _contact(msg.get("contact"))}
    if kind == "send":
        key = msg.get("idempotency_key")
        if not isinstance(key, str) or not IDEMPOTENCY.match(key):
            raise MessagingError("invalid")
        text = _short(msg.get("text"), 10 * MAX_TEXT_BYTES, "invalid")
        if len(text.encode("utf-8", "surrogatepass")) > MAX_TEXT_BYTES:
            raise MessagingError("too_long")
        return {"op": "send", "contact": _contact(msg.get("contact")), "text": text, "idempotency_key": key}
    if kind == "retry":
        message_id = msg.get("message_id")
        if not isinstance(message_id, str) or not MESSAGE_ID.match(message_id):
            raise MessagingError("invalid")
        return {"op": "retry", "message_id": message_id}
    if kind == "contact_add":
        return {
            "op": "contact_add",
            "name": _short(msg.get("name"), 128, "invalid_name"),
            "address": _short(msg.get("address"), 128, "invalid_address"),
        }
    if kind == "contact_rename":
        name = _short(msg.get("name"), 128, "invalid_name")
        return {"op": "contact_rename", "contact": _contact(msg.get("contact")), "name": name}
    raise MessagingError("invalid")


COMMANDS: dict[str, dict[Any, Any]] = {
    "conversations": {},
    "history": {probatio.Required("contact"): str, probatio.Optional("before"): int},
    "read": {probatio.Required("contact"): str},
    "clear": {probatio.Required("contact"): str},
    "send": {
        probatio.Required("contact"): str,
        probatio.Required("text"): str,
        probatio.Required("idempotency_key"): str,
    },
    "retry": {probatio.Required("message_id"): str},
    "contact_add": {probatio.Required("name"): str, probatio.Required("address"): str},
    "contact_rename": {probatio.Required("contact"): str, probatio.Required("name"): str},
    "contact_remove": {probatio.Required("contact"): str},
}


def _make_command(kind: str, extra: dict[Any, Any]) -> Any:
    schema = {probatio.Required("type"): f"{WS_PREFIX}/{kind}", probatio.Required("entry_id"): str, **extra}

    @require_admin
    @websocket_command(schema)
    @async_response
    async def handler(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
        hub: MessagingHub | None = None
        try:
            hub = _hub(hass, msg["entry_id"])
            answer = await hub.request(build_request(kind, msg))
        except MessagingError as exc:
            code = exc.code
            if code == "rate_limited" and hub is not None:
                hub._log_refusal(kind, code)
                # The app uses one code for both allowances; only a send is "too many messages".
                if kind != "send":
                    code = "busy"
            connection.send_error(msg["id"], code, code)
            return
        answer.pop("ok", None)
        if kind in CHANGES:  # never a read: the panel reads on every announcement
            hub.notify({"type": "changed"})
        connection.send_result(msg["id"], answer)

    handler.__name__ = f"ws_messaging_{kind}"
    return handler


@require_admin
@websocket_command({probatio.Required("type"): f"{WS_PREFIX}/subscribe", probatio.Required("entry_id"): str})
@callback
def ws_subscribe(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """Events {"type": "changed"} and {"type": "unavailable", "error": code}: never content."""
    try:
        hub = _hub(hass, msg["entry_id"])
    except MessagingError as exc:
        connection.send_error(msg["id"], exc.code, exc.code)
        return

    @callback
    def forward(event: dict[str, Any]) -> None:
        connection.send_message(event_message(msg["id"], event))

    connection.send_result(msg["id"])  # first: the first event may follow at once
    connection.subscriptions[msg["id"]] = hub.subscribe(forward)


HANDLERS = [_make_command(kind, extra) for kind, extra in COMMANDS.items()]


def async_register(hass: HomeAssistant) -> None:
    for handler in HANDLERS:
        websocket_api.async_register_command(hass, handler)
    websocket_api.async_register_command(hass, ws_subscribe)
