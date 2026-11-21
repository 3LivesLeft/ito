# SPDX-License-Identifier: Apache-2.0
"""App and integration versions: repairs that say which one to update (M1, compatibility.py)."""

import json
from pathlib import Path

import pytest
from homeassistant.helpers import issue_registry as ir

from custom_components.meshbeacon.compatibility import ISSUE_APP_OUTDATED, ISSUE_INTEGRATION_OUTDATED, mismatch
from custom_components.meshbeacon.const import DOMAIN

from .conftest import URL, snapshot

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION_VERSION = json.loads((ROOT / "custom_components/meshbeacon/manifest.json").read_text())["version"]


@pytest.mark.parametrize(
    ("app", "integration", "expected"),
    [
        ("0.3.0", "0.3.0", None),
        ("0.3.4", "0.3.1", None),  # patch releases never matter
        ("0.2.0", "0.3.0", None),  # N−1: the v0.2 app with the v0.3 integration (the migration path)
        ("0.1.2", "0.3.0", ISSUE_APP_OUTDATED),
        ("0.4.0", "0.3.0", ISSUE_INTEGRATION_OUTDATED),
        ("1.0.0", "0.9.0", ISSUE_INTEGRATION_OUTDATED),
        ("0.9.0", "1.0.0", ISSUE_APP_OUTDATED),
        (None, "0.3.0", None),
        ("0.3.0-dev", "0.3.0", None),  # unparseable: no guess
        ("0.3.0", None, None),
    ],
)
def test_rule(app, integration, expected):
    assert mismatch(app, integration) == expected


def with_version(version):
    data = snapshot()
    data["app"]["version"] = version
    return data


def bump(version, minor):
    major, mid, _ = (int(x) for x in version.split("."))
    return f"{major}.{mid + minor}.0"


async def test_matching_versions_raise_no_repair(hass, mock_entry, aioclient_mock):
    aioclient_mock.get(URL, json=with_version(INTEGRATION_VERSION))
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, ISSUE_APP_OUTDATED) is None
    assert registry.async_get_issue(DOMAIN, ISSUE_INTEGRATION_OUTDATED) is None


async def test_newer_app_asks_to_update_the_integration(hass, mock_entry, aioclient_mock):
    aioclient_mock.get(URL, json=with_version(bump(INTEGRATION_VERSION, 1)))
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_INTEGRATION_OUTDATED)
    assert issue is not None and issue.translation_key == ISSUE_INTEGRATION_OUTDATED
    assert issue.translation_placeholders == {
        "app_version": bump(INTEGRATION_VERSION, 1),
        "integration_version": INTEGRATION_VERSION,
    }
    assert issue.learn_more_url and issue.learn_more_url.endswith("#updating")
    assert hass.states.get("sensor.ito_status").state == "running"  # still works meanwhile


async def test_repair_goes_once_the_app_is_updated(hass, mock_entry, aioclient_mock):
    """The app is two minors behind (raises a repair), then the user updates it."""
    old = "0.0.1" if INTEGRATION_VERSION.split(".")[1] in ("0", "1") else bump(INTEGRATION_VERSION, -2)
    aioclient_mock.get(URL, json=with_version(old))
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    registry = ir.async_get(hass)
    if mismatch(old, INTEGRATION_VERSION) is None:
        pytest.skip("no older minor release exists to test against")
    assert registry.async_get_issue(DOMAIN, ISSUE_APP_OUTDATED) is not None
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=with_version(INTEGRATION_VERSION))
    await mock_entry.runtime_data.async_refresh()
    assert registry.async_get_issue(DOMAIN, ISSUE_APP_OUTDATED) is None


async def test_unloading_clears_version_repairs(hass, mock_entry, aioclient_mock):
    aioclient_mock.get(URL, json=with_version(bump(INTEGRATION_VERSION, 1)))
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_INTEGRATION_OUTDATED) is None


def test_every_issue_has_a_translation():
    strings = json.loads((ROOT / "custom_components/meshbeacon/strings.json").read_text())
    english = json.loads((ROOT / "custom_components/meshbeacon/translations/en.json").read_text())
    for issue in (ISSUE_APP_OUTDATED, ISSUE_INTEGRATION_OUTDATED):
        for table in (strings, english):
            text = table["issues"][issue]
            assert text["title"] and "{app_version}" in text["description"]
            assert "{integration_version}" in text["description"]
