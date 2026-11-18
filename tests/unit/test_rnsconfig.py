# SPDX-License-Identifier: Apache-2.0
"""Configuration injection regression tests (testing strategy §4.2)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from RNS.vendor.configobj import ConfigObj

from meshbeacon import rnsconfig
from meshbeacon.settings import Peer, Settings, valid_host, valid_name, valid_passphrase

KEY = "ab" * 32


def parsed(text):
    return ConfigObj(text.splitlines())


def test_render_basic_structure():
    s = Settings(peers=(Peer("Home", "rns.example.org", 4242),), transport=True)
    cfg = parsed(rnsconfig.render(s, KEY))
    assert cfg["reticulum"]["enable_transport"] == "Yes"
    assert cfg["reticulum"]["share_instance"] == "No"
    assert cfg["reticulum"]["rpc_key"] == KEY
    assert list(cfg["interfaces"].keys()) == ["Home"]
    assert cfg["interfaces"]["Home"]["type"] == "TCPClientInterface"
    assert cfg["interfaces"]["Home"]["target_port"] == "4242"


def test_defaults_render_no_interfaces_and_transport_off():
    cfg = parsed(rnsconfig.render(Settings(), KEY))
    assert cfg["reticulum"]["enable_transport"] == "No"
    assert dict(cfg["interfaces"]) == {}


@pytest.mark.parametrize("level,expected", [("quiet", "2"), ("normal", "4"), ("detailed", "5")])
def test_log_levels(level, expected):
    cfg = parsed(rnsconfig.render(Settings(log_level=level), KEY))
    assert cfg["logging"]["loglevel"] == expected


def test_rpc_key_is_random_hex():
    a, b = rnsconfig.new_rpc_key(), rnsconfig.new_rpc_key()
    assert a != b and len(bytes.fromhex(a)) == 32


def test_invalid_rpc_key_refused():
    with pytest.raises(ValueError):
        rnsconfig.render(Settings(), "not-hex")


def test_phase0_injection_reproduction_cannot_happen():
    """Phase 0 showed naive templating of this host adds an AutoInterface. Validation rejects it,
    and even if a hostile value bypassed validation, object-API rendering keeps the structure."""
    hostile = "peer.example\n  [[Injected]]\n    type = AutoInterface\n    enabled = yes"
    assert not valid_host(hostile)
    s = Settings(peers=(Peer("Home", hostile, 4242),))
    try:
        text = rnsconfig.render(s, KEY)
    except rnsconfig.RenderError:
        return
    cfg = parsed(text)
    assert list(cfg["interfaces"].keys()) == ["Home"]
    assert "AutoInterface" not in [v.get("type") for v in cfg["interfaces"].values()]


@pytest.mark.parametrize(
    "value", ["a.example, b.example", "%(enable_transport)s", "$x", "x # y", "x\ny", '"""', "'x'", "\\"]
)
def test_hostile_values_never_change_structure(value):
    s = Settings(peers=(Peer("Home", "rns.example.org", 4242, passphrase=value),))
    try:
        text = rnsconfig.render(s, KEY)
    except rnsconfig.RenderError:
        return  # refused: also acceptable
    rnsconfig.verify(text, rnsconfig.intended_structure(s, KEY))


def test_forbidden_keys_detected():
    bad = rnsconfig.intended_structure(Settings(), KEY)
    bad["reticulum"]["discover_interfaces"] = "Yes"
    with pytest.raises(rnsconfig.RenderError):
        rnsconfig._check_forbidden(bad)
    bad2 = rnsconfig.intended_structure(Settings(), KEY)
    bad2["interfaces"]["x"] = {"type": "AutoInterface"}
    with pytest.raises(rnsconfig.RenderError):
        rnsconfig._check_forbidden(bad2)


def test_verify_detects_extra_section():
    s = Settings(peers=(Peer("Home", "rns.example.org", 4242),))
    text = rnsconfig.render(s, KEY) + "[[Extra]]\ntype = AutoInterface\n"
    with pytest.raises(rnsconfig.RenderError):
        rnsconfig.verify(text, rnsconfig.intended_structure(s, KEY))


# Generate valid values directly (filtering random text discards too many inputs); the filters
# remain only as a guard that the generators stay in step with the validators.
names = st.from_regex(r"[A-Za-z0-9](?:[A-Za-z0-9 _.-]{0,30}[A-Za-z0-9_.-])?", fullmatch=True).filter(valid_name)
hosts = st.from_regex(r"[a-z0-9]{1,10}(\.[a-z0-9]{1,10}){0,3}", fullmatch=True).filter(valid_host)
_PC = r"[!&()*+\-./0-9:;<=>?@A-Z\[\]^_`a-z{|}~]"  # allowed passphrase characters except space
phrases = st.from_regex(rf"{_PC}(?:[ {_PC[1:-1]}]{{0,38}}{_PC})?", fullmatch=True).filter(valid_passphrase)


@settings(max_examples=300, deadline=None)
@given(
    st.lists(
        st.tuples(names, hosts, st.integers(1, 65535), st.one_of(st.none(), names), st.one_of(st.none(), phrases)),
        max_size=4,
        unique_by=lambda t: t[0].casefold(),
    ),
    st.booleans(),
)
def test_fuzz_validated_input_always_renders_exact_structure(peers, transport):
    s = Settings(peers=tuple(Peer(*p) for p in peers), transport=transport)
    text = rnsconfig.render(s, KEY)
    cfg = parsed(text)
    assert set(cfg.keys()) == {"reticulum", "logging", "interfaces"}
    assert list(cfg["interfaces"].keys()) == [p[0] for p in peers]
    for iface in cfg["interfaces"].values():
        assert iface["type"] == "TCPClientInterface"
        assert not (set(iface.keys()) & rnsconfig.FORBIDDEN_KEYS)
    assert not (set(cfg["reticulum"].keys()) & rnsconfig.FORBIDDEN_KEYS)
