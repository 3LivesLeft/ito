# SPDX-License-Identifier: Apache-2.0
"""Static checks of the app packaging against the approved security posture (roadmap LP-11)."""

import re
from pathlib import Path

import yaml

from meshbeacon.settings import ALLOWED_PEER_KEYS, ALLOWED_TOP_LEVEL

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "meshbeacon"
CONFIG = yaml.safe_load((APP / "config.yaml").read_text())

FORBIDDEN_TRUE = [
    "host_network",
    "host_pid",
    "host_ipc",
    "host_uts",
    "host_dbus",
    "hassio_api",
    "homeassistant_api",
    "auth_api",
    "docker_api",
    "full_access",
    "uart",
    "usb",
    "gpio",
    "udev",
    "devicetree",
    "kernel_modules",
    "video",
    "audio",
    "stdin",
    "realtime",
    "journald",
    "ingress",
]


def test_no_elevated_permissions():
    for key in FORBIDDEN_TRUE:
        assert not CONFIG.get(key), key
    assert not CONFIG.get("privileged")
    assert not CONFIG.get("devices")
    assert not CONFIG.get("ports")
    assert not CONFIG.get("map")
    assert CONFIG.get("hassio_role", "default") == "default"
    assert CONFIG["apparmor"] is True and (APP / "apparmor.txt").exists()


def test_identity_and_stage():
    assert CONFIG["slug"] == "meshbeacon"
    assert CONFIG["stage"] == "experimental"
    assert set(CONFIG["arch"]) == {"aarch64", "amd64"}
    assert CONFIG["init"] is False
    assert "image" not in CONFIG  # not published: local builds only until the release gates are met


def test_watchdog_uses_internal_health_endpoint():
    assert CONFIG["watchdog"] == "http://[HOST]:[PORT:8099]/health"


def test_defaults_make_no_external_connections():
    assert CONFIG["options"]["peers"] == []
    assert CONFIG["options"]["transport"] is False
    assert CONFIG["options"]["replace_identity"] is False
    assert CONFIG["options"]["home_assistant_integration"] is False  # opt-in until ADR 0006 is approved


def test_discovery_is_the_only_new_supervisor_feature():
    # ADR 0006: discovery needs no hassio_api permission and does not change the security rating.
    assert CONFIG["discovery"] == ["meshbeacon"]
    assert "ports" not in CONFIG and "ingress" not in CONFIG


def test_schema_matches_core_validation():
    assert set(CONFIG["schema"]) == ALLOWED_TOP_LEVEL == set(CONFIG["options"])
    assert set(CONFIG["schema"]["peers"][0]) == ALLOWED_PEER_KEYS
    translations = yaml.safe_load((APP / "translations" / "en.yaml").read_text())["configuration"]
    assert set(translations) == ALLOWED_TOP_LEVEL


def test_apparmor_profile_name_matches_slug():
    assert re.search(r"^profile meshbeacon ", (APP / "apparmor.txt").read_text(), re.M)


def test_dockerfile_base_pinned_by_digest():
    first_from = next(line for line in (APP / "Dockerfile").read_text().splitlines() if line.startswith("FROM"))
    assert re.search(r"@sha256:[0-9a-f]{64}$", first_from)


def test_requirements_hash_pinned_and_rns_unmodified():
    text = (APP / "requirements.txt").read_text()
    reqs = [line for line in text.splitlines() if line and not line.startswith((" ", "#"))]
    for req in reqs:
        assert re.match(r"^[a-z0-9_-]+==[0-9][^ ]* \\$", req), req
    assert "rns==1.6.0 \\" in reqs
    assert text.count("--hash=sha256:") >= len(reqs)


def test_licence_copies_match_root():
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES"):
        assert (APP / name).read_bytes() == (ROOT / name).read_bytes(), name
    assert "The Software shall not be used" in (ROOT / "THIRD_PARTY_NOTICES").read_text()
