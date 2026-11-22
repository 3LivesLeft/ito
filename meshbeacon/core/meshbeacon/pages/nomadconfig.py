# SPDX-License-Identifier: Apache-2.0
"""The Nomad Network daemon's configuration (ADR 0027 point 4).

Built with ConfigObj's object API (the parser RNS vendors and Nomad Network reads it with) from
fixed values plus the validated node name, then re-parsed and compared (rule 12). Every value
here closes something the daemon would otherwise do on its own:

- ``[client]``: its own LXMF address is never announced, no periodic sync with an automatically
  chosen propagation node, no propagation fallback; messages to it must carry a stamp of cost 16
  and be at most 1 KB (anyone who sees the node announce could otherwise fill its storage).
- ``[node]``: a page host only. No LXMF propagation; announced at start and every 6 hours; pages
  re-read every minute; an empty files folder.
- ``[logging]``: to the console (the core redacts it); ``[printing]`` off.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import valid_node_name

LOGLEVELS = {"quiet": "2", "normal": "3", "detailed": "4"}
ANNOUNCE_MINUTES = "360"


class ConfigError(Exception):
    pass


def structure(node_name: str, pages_path: Path, files_path: Path, log_level: str = "normal") -> dict[str, Any]:
    if not valid_node_name(node_name):
        raise ConfigError("invalid node name")
    if log_level not in LOGLEVELS:
        raise ConfigError("invalid log level")
    for path in (pages_path, files_path):
        text = str(path)
        if not path.is_absolute() or any(ch in text for ch in "\"'#,\n\r=[]$%\\"):
            raise ConfigError("invalid path")
    return {
        "logging": {"loglevel": LOGLEVELS[log_level], "destination": "console"},
        "client": {
            "enable_client": "no",
            "user_interface": "none",
            "announce_at_start": "no",
            "periodic_lxmf_sync": "no",
            "try_propagation_on_send_fail": "no",
            "required_stamp_cost": "16",
            "accept_invalid_stamps": "no",
            "max_accepted_size": "1",
            "notify_on_new_message": "no",
        },
        "textui": {},
        "node": {
            "enable_node": "yes",
            "node_name": node_name,
            "announce_at_start": "yes",
            "announce_interval": ANNOUNCE_MINUTES,
            "pages_path": str(pages_path),
            "files_path": str(files_path),
            "page_refresh_interval": "1",
            "file_refresh_interval": "0",
            "disable_propagation": "yes",
            "message_storage_limit": "1",
            "max_peers": "0",
        },
        "printing": {"print_messages": "no"},
    }


def _configobj() -> Any:
    from RNS.vendor.configobj import ConfigObj

    return ConfigObj


def _plain(section: Any) -> dict[str, Any]:
    out: dict[str, Any] = {key: section[key] for key in section.scalars}
    for key in section.sections:
        out[key] = _plain(section[key])
    return out


def render(node_name: str, pages_path: Path, files_path: Path, log_level: str = "normal") -> str:
    expected = structure(node_name, pages_path, files_path, log_level)
    config_obj = _configobj()
    cfg = config_obj()
    cfg.initial_comment = ["# Written by ito at every start of page hosting. Do not edit: changes are overwritten."]
    for section, values in expected.items():
        cfg[section] = {}
        for key, value in values.items():
            cfg[section][key] = value
    text = "\n".join(cfg.write()) + "\n"
    try:
        parsed = _plain(config_obj(text.splitlines()))
    except Exception as exc:
        raise ConfigError("the configuration does not parse") from exc
    if parsed != expected:
        raise ConfigError("the configuration does not match the intended structure")
    return text
