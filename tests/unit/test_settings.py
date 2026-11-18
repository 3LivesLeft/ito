# SPDX-License-Identifier: Apache-2.0
import pytest
from hypothesis import given
from hypothesis import strategies as st

from meshbeacon.settings import (
    MAX_PEERS,
    ValidationError,
    parse_options,
    valid_host,
    valid_name,
    valid_passphrase,
)


def peer(**kw):
    base = {"name": "Home", "host": "rns.example.org", "port": 4242}
    base.update(kw)
    return base


def test_defaults_are_safe():
    s = parse_options({})
    assert s.peers == ()
    assert s.transport is False
    assert s.log_level == "normal"
    assert s.replace_identity is False


def test_valid_peer():
    s = parse_options({"peers": [peer(network_name="mynet", passphrase="correct horse")]})
    assert s.peers[0].host == "rns.example.org"
    assert s.secrets == ("correct horse",)


@pytest.mark.parametrize(
    "host",
    ["rns.example.org", "a", "x-y.example", "xn--bcher-kva.example", "192.0.2.10", "2001:db8::1", "::1", "localhost"],
)
def test_hosts_accepted(host):
    assert valid_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "",
        "peer.example\n  [[Injected]]",
        "a.example, b.example",
        "%(enable_transport)s",
        "$enable_transport",
        "peer.example # x",
        "peer.example.",
        "-bad.example",
        "bad-.example",
        "a..b",
        "a" * 254,
        ("a" * 64) + ".example",
        "fe80::1%eth0",
        "192.0.2.10:4242",
        "300.1.1.1",
        "bücher.example",
        "peer.example\r",
        "peer\x00.example",
        "peer.example\u2028",
        "peer\u202e.example",
        "http://peer.example",
        "peer example",
        "[[x]]",
    ],
)
def test_hosts_rejected(host):
    assert not valid_host(host)


@pytest.mark.parametrize("name", ["Home", "My peer", "peer_1", "a.b-c", "A" * 32])
def test_names_accepted(name):
    assert valid_name(name)


@pytest.mark.parametrize(
    "name",
    ["", " lead", "trail ", "a]]", "[[a", "a=b", "a#b", "a,b", "a%b", "a$b", "a'b", 'a"b', "a\nb", "A" * 33, "café"],
)
def test_names_rejected(name):
    assert not valid_name(name)


@pytest.mark.parametrize("value", ["x", "correct horse battery staple", "p@ss:w0rd!(x)[y]{z}=+-*/<>?^_|~&;."])
def test_passphrases_accepted(value):
    assert valid_passphrase(value)


@pytest.mark.parametrize(
    "value", ["", " x", "x ", "a#b", "a,b", "a%b", "a$b", "a'b", 'a"b', "a\\b", "a\nb", "a\tb", "pässword", "x" * 129]
)
def test_passphrases_rejected(value):
    assert not valid_passphrase(value)


def test_unknown_options_rejected():
    with pytest.raises(ValidationError):
        parse_options({"discover_interfaces": True})
    with pytest.raises(ValidationError):
        parse_options({"peers": [peer(type="AutoInterface")]})


def test_duplicate_names_case_insensitive():
    with pytest.raises(ValidationError) as exc:
        parse_options({"peers": [peer(name="Home"), peer(name="home")]})
    assert "Two peers" in str(exc.value)


def test_too_many_peers():
    with pytest.raises(ValidationError):
        parse_options({"peers": [peer(name=f"p{i}") for i in range(MAX_PEERS + 1)]})


@pytest.mark.parametrize("port", [0, 65536, "4242", True, None, 4.5])
def test_bad_ports(port):
    with pytest.raises(ValidationError):
        parse_options({"peers": [peer(port=port)]})


@pytest.mark.parametrize(
    "options",
    [
        {"transport": "yes"},
        {"log_level": "debug"},
        {"memory_limit_mb": 64},
        {"memory_limit_mb": 4096},
        {"replace_identity": 1},
        {"peers": "rns.example.org"},
        {"peers": ["rns.example.org"]},
        [],
    ],
)
def test_bad_values(options):
    with pytest.raises(ValidationError):
        parse_options(options)


def test_error_messages_are_plain_and_do_not_echo_passphrase():
    with pytest.raises(ValidationError) as exc:
        parse_options({"peers": [peer(passphrase="bad#secret")]})
    assert "bad#secret" not in str(exc.value)
    assert "passphrase" in str(exc.value)


@given(st.text(max_size=300))
def test_fuzz_host_never_contains_structure_characters(text):
    if valid_host(text):
        assert not any(c in text for c in "\n\r[]#,%$\"'= \\")


@given(st.text(max_size=60))
def test_fuzz_name_never_contains_structure_characters(text):
    if valid_name(text):
        assert not any(c in text for c in "\n\r[]#,%$\"'=\\")
        assert text == text.strip()
