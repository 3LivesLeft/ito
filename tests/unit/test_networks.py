# SPDX-License-Identifier: Apache-2.0
"""The public network selector (ADR 0004): presets, invalid input, persistence and upgrades.

Nothing here connects anywhere: presets are only validated and rendered to configuration text.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest
import yaml
from RNS.vendor.configobj import ConfigObj

from meshbeacon import networks, rnsconfig
from meshbeacon.paths import Paths
from meshbeacon.settings import MAX_PEERS, ValidationError, parse_options, valid_host, valid_name
from meshbeacon.supervisor import Supervisor

ROOT = Path(__file__).resolve().parents[2]
CONFIG = yaml.safe_load((ROOT / "meshbeacon" / "config.yaml").read_text())
KEY = "ab" * 32

# The endpoints as their operators publish them (docs/research/public-peers.md §2).
PUBLISHED = {
    "ratspeak_ruby": ("Ratspeak Ruby", "1.ratspeak.org", 4141),
    "ratspeak_emerald": ("Ratspeak Emerald", "2.ratspeak.org", 4242),
    "ratspeak_diamond": ("Ratspeak Diamond", "3.ratspeak.org", 4343),
    "reticulumnet": ("ReticulumNet", "node.reticulumnet.nl", 4242),
}


def interfaces(options: dict) -> dict:
    text = rnsconfig.render(parse_options(options), KEY)
    return ConfigObj(text.splitlines())["interfaces"].dict()


# -- the preset data ---------------------------------------------------------------------------
def test_presets_match_the_published_endpoints():
    got = {n.id: (n.name, n.host, n.port) for n in networks.presets().values()}
    assert got == PUBLISHED


def test_every_preset_is_valid_and_cites_a_primary_source():
    for n in networks.presets().values():
        assert valid_name(n.name) and valid_host(n.host) and 1 <= n.port <= 65535
        assert n.host == n.host.lower()
        assert n.source.startswith("https://") and n.operator and n.documented_on
        # ADR 0004 V1–V7 are manual release checks by the maintainer; check_release.py refuses a
        # tag until each preset records them. This branch never fakes that record.
        assert n.release_checks_passed_on is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", n.release_checks_passed_on)
    assert "custom" not in networks.presets()


def test_presets_need_no_network_credentials():
    """None of the operators publishes an IFAC network name or passphrase for these entry points."""
    for preset_id in networks.presets():
        peer = parse_options({"network": preset_id}).peers[0]
        assert peer.network_name is None and peer.passphrase is None


def test_the_supervisor_dropdown_offers_exactly_the_presets():
    match = re.fullmatch(r"list\((.*)\)", CONFIG["schema"]["network"])
    assert match and tuple(match.group(1).split("|")) == networks.choices()
    assert networks.choices()[0] == "custom"


# -- selection configures the real transport interface ------------------------------------------
@pytest.mark.parametrize("preset_id", list(PUBLISHED))
def test_selecting_a_preset_renders_a_tcp_client_interface(preset_id):
    name, host, port = PUBLISHED[preset_id]
    assert interfaces({"network": preset_id}) == {
        name: {"type": "TCPClientInterface", "enabled": "yes", "target_host": host, "target_port": str(port)}
    }
    assert parse_options({"network": preset_id}).network == preset_id


def test_custom_adds_no_interface():
    assert interfaces({"network": "custom"}) == {}
    home = {"name": "Home", "host": "rns.example.org", "port": 4242}
    expected = {"type": "TCPClientInterface", "enabled": "yes", "target_host": "rns.example.org", "target_port": "4242"}
    assert interfaces({"network": "custom", "peers": [home]}) == {"Home": expected}


def test_a_preset_keeps_multiple_own_peers_with_their_credentials():
    own = [
        {"name": "Home", "host": "rns.example.org", "port": 4242, "network_name": "mynet", "passphrase": "secret pass"},
        {"name": "Cabin", "host": "192.0.2.10", "port": 4965},
    ]
    s = parse_options({"network": "reticulumnet", "peers": own})
    assert [p.name for p in s.peers] == ["ReticulumNet", "Home", "Cabin"]
    assert s.secrets == ("secret pass",)
    rendered = interfaces({"network": "reticulumnet", "peers": own})
    assert list(rendered) == ["ReticulumNet", "Home", "Cabin"]
    assert rendered["Home"]["network_name"] == "mynet"


def test_a_preset_does_not_count_towards_the_peer_limit():
    own = [{"name": f"P{i}", "host": "rns.example.org", "port": 4000 + i} for i in range(MAX_PEERS)]
    assert len(parse_options({"network": "ratspeak_ruby", "peers": own}).peers) == MAX_PEERS + 1


# -- invalid input ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value",
    ["emerald", "Ratspeak Emerald", "RATSPEAK_RUBY", "custom\n", "reticulumnet]]\n[[x", 1, True, ["custom"], {}],
)
def test_unknown_network_values_are_refused(value):
    with pytest.raises(ValidationError) as exc:
        parse_options({"network": value})
    assert any("'network' must be one of" in p for p in exc.value.problems)


@pytest.mark.parametrize(
    "bad",
    [
        {"name": "Home", "host": "bad\nhost", "port": 4242},
        {"name": "Home", "host": "rns.example.org:4242", "port": 4242},
        {"name": "Home", "host": "rns.example.org", "port": 0},
        {"name": "Home", "host": "rns.example.org", "port": 70000},
        {"name": "Home", "host": "rns.example.org", "port": "4242"},
        {"name": "[[Home]]", "host": "rns.example.org", "port": 4242},
    ],
)
def test_invalid_own_endpoints_are_still_refused_with_a_preset(bad):
    with pytest.raises(ValidationError):
        parse_options({"network": "ratspeak_emerald", "peers": [bad]})


def test_an_own_peer_with_the_presets_name_but_another_endpoint_is_refused():
    with pytest.raises(ValidationError) as exc:
        own = {"name": "ratspeak ruby", "host": "192.0.2.1", "port": 1}
        parse_options({"network": "ratspeak_ruby", "peers": [own]})
    assert any("same as the public network" in p for p in exc.value.problems)


# -- persistence and upgrades ------------------------------------------------------------------
def test_the_default_is_custom_and_makes_no_connection():
    assert CONFIG["options"]["network"] == "custom"
    s = parse_options({"network": CONFIG["options"]["network"], "peers": CONFIG["options"]["peers"]})
    assert s.network == "custom" and s.peers == ()


def test_the_selection_survives_a_save_and_restart():
    """Supervisor stores options as JSON (options.json); every start re-reads and re-renders."""
    options = {"network": "ratspeak_diamond", "peers": [{"name": "Home", "host": "rns.example.org", "port": 4242}]}
    stored = json.loads(json.dumps(options))
    assert parse_options(stored) == parse_options(options)
    assert interfaces(stored) == interfaces(options)


@pytest.mark.parametrize("network", [None, ""])
def test_options_saved_before_the_selector_existed_are_unchanged(network):
    """An installation upgraded from 0.3.0 has no ``network`` key (or an empty one): its peers,
    and so its Reticulum configuration, stay exactly as they were."""
    old = {
        "peers": [{"name": "Home", "host": "rns.example.org", "port": 4242}],
        "transport": False,
        "log_level": "normal",
        "memory_limit_mb": 256,
        "replace_identity": False,
        "home_assistant_integration": False,
    }
    upgraded = dict(old) if network is None else {**old, "network": network}
    assert parse_options(upgraded).network == "custom"
    assert parse_options(upgraded).peers == parse_options(old).peers
    assert rnsconfig.render(parse_options(upgraded), KEY) == rnsconfig.render(parse_options(old), KEY)


@pytest.mark.parametrize("host", ["2.ratspeak.org", "2.RATSPEAK.org"])
def test_a_peer_typed_in_by_hand_is_not_duplicated_when_its_preset_is_selected(host):
    own = {"name": "Emerald", "host": host, "port": 4242, "network_name": "x1", "passphrase": "kept"}
    s = parse_options({"network": "ratspeak_emerald", "peers": [own]})
    assert [p.name for p in s.peers] == ["Emerald"]
    assert s.peers[0].passphrase == "kept"  # the user's own entry is kept exactly as it was


# -- the selection is shown --------------------------------------------------------------------
def startup_log(tmp_path: Path, options: dict) -> str:
    out = io.StringIO()
    sup = Supervisor(Paths(data=tmp_path), out=out, health_port=0, api_port=0)
    sup.settings = parse_options(options)
    sup.startup_report()
    return out.getvalue()


def test_the_log_names_the_selected_network_and_its_peer(tmp_path):
    log = startup_log(tmp_path, {"network": "ratspeak_emerald"})
    assert "Public network: Ratspeak Emerald (run by Ratspeak)." in log
    assert "Peer configured: Ratspeak Emerald (2.ratspeak.org, port 4242)." in log
    assert "Public network: none" in startup_log(tmp_path, {})


def test_diamond_with_transport_mode_warns(tmp_path):
    assert "Diamond bans nodes" in startup_log(tmp_path, {"network": "ratspeak_diamond", "transport": True})
    assert "Diamond bans nodes" not in startup_log(tmp_path, {"network": "ratspeak_diamond"})
    assert "Diamond bans nodes" not in startup_log(tmp_path, {"network": "ratspeak_ruby", "transport": True})
