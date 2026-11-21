# SPDX-License-Identifier: Apache-2.0
"""Which node an entry describes, independent of the app that currently serves it.

Version 1 entries used the app's slug both as the entry's unique ID and as the prefix of every
entity's unique ID. A slug is the app's install location, not the node: it changes when the app
moves, for example from a local app (``local_meshbeacon``) to the published app
(``<repository hash>_meshbeacon``). Version 2 keeps two separate values in the entry's data:

- ``node_key``: the prefix of every entity and device unique ID. Set once and never changed, so
  entity IDs, names, areas and recorder history survive any later change of app.
- ``app_slug``: the app this entry talks to now. Discovery and the key refresh match on it.

Migrating v1 to v2 sets both to the old unique ID, so nothing changes for existing installations.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import CONF_APP_SLUG, CONF_NODE_KEY


def node_key(entry: ConfigEntry[Any]) -> str:
    key = entry.data.get(CONF_NODE_KEY)
    if isinstance(key, str) and key:
        return key
    return entry.unique_id or entry.entry_id


def app_slug(entry: ConfigEntry[Any]) -> str | None:
    slug = entry.data.get(CONF_APP_SLUG)
    if isinstance(slug, str) and slug:
        return slug
    return entry.unique_id
