# SPDX-License-Identifier: Apache-2.0
import base64
import os

from meshbeacon.logfilter import REDACTED, RateLimiter, Redactor


def test_redacts_rns_hash_format():
    line = "[Verbose] Identity keys created for <da5639d726b26afcc6359837c6161541>"
    assert "da5639d7" not in Redactor()(line)
    assert REDACTED in Redactor()(line)


def test_redacts_bare_hashes_keys_and_base64():
    key = os.urandom(64)
    r = Redactor()
    for text in (key.hex(), key.hex().upper(), base64.b64encode(key).decode(), os.urandom(16).hex()):
        assert text not in r(f"value {text} end")


def test_redacts_known_secrets():
    assert "correct horse" not in Redactor(["correct horse"])("passphrase correct horse here")


def test_keeps_ordinary_text():
    line = "[Notice] Started rnsd version 1.6.0 on TCPInterface[Home/rns.example.org:4242]"
    assert Redactor()(line) == line


def test_truncates_and_strips_control():
    out = Redactor()("a" * 5000 + "\x1b[31m")
    assert len(out) < 1100 and "\x1b" not in out


def test_rate_limiter():
    now = [0.0]
    rl = RateLimiter(rate=20, burst=100, clock=lambda: now[0])
    allowed = sum(rl.allow() for _ in range(1000))
    assert allowed == 100
    assert rl.take_suppressed() == 900
    now[0] += 1.0
    assert sum(rl.allow() for _ in range(100)) == 20


def test_keeps_file_paths():
    line = '  File "/usr/lib/python3.13/site-packages/meshbeacon/core/meshbeacon/prepare.py", line 1'
    assert Redactor()(line) == line
