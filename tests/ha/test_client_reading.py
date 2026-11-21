# SPDX-License-Identifier: Apache-2.0
"""Complete, bounded reading of status responses (v0.2 review follow-up).

A single ``StreamReader.read(n)`` returns only the bytes that have arrived so far, so a response
split across TLS records, TCP segments or HTTP chunks could be cut short and rejected as "not
JSON". These tests use a real TLS server on 127.0.0.1 with a pinned throwaway certificate (the
same one the app makes), sending the reply in deliberately small, delayed pieces, so that each
read sees a fragment rather than the whole body.
"""

from __future__ import annotations

import asyncio
import json
import ssl
from collections.abc import AsyncIterator
from pathlib import Path

import aiohttp
import pytest

from custom_components.meshbeacon.client import (
    MAX_RESPONSE,
    MeshBeaconClient,
    MeshBeaconError,
    SchemaError,
    read_bounded,
)
from meshbeacon.tlscert import generate

from .conftest import TOKEN
from .fixtures import snapshot

# Real sockets on 127.0.0.1 only: the harness keeps its loopback-only host allow-list in force.


async def _pieces(writer: asyncio.StreamWriter, data: bytes, size: int) -> None:
    for start in range(0, len(data), size):
        writer.write(data[start : start + size])
        await writer.drain()
        await asyncio.sleep(0.001)  # one TLS record per piece, delivered separately


def _head(length: int | None, chunked: bool = False) -> bytes:
    lines = ["HTTP/1.1 200 OK", "Content-Type: application/json", "Connection: close"]
    if chunked:
        lines.append("Transfer-Encoding: chunked")
    elif length is not None:
        lines.append(f"Content-Length: {length}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


class _Server:
    def __init__(self, reply) -> None:
        self.reply = reply
        self.requests: list[bytes] = []

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            self.requests.append(await reader.readuntil(b"\r\n\r\n"))
            await self.reply(writer)
        except (ConnectionError, ssl.SSLError, asyncio.IncompleteReadError):
            pass  # the client may hang up early on purpose (oversized replies)
        finally:
            writer.close()


@pytest.fixture
async def tls(tmp_path: Path, socket_enabled) -> AsyncIterator[tuple[ssl.SSLContext, str]]:
    fingerprint = generate(tmp_path)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(tmp_path / "cert.pem", tmp_path / "key.pem")
    yield context, fingerprint


async def _fetch(tls, reply):
    context, fingerprint = tls
    server_state = _Server(reply)
    server = await asyncio.start_server(server_state.handle, "127.0.0.1", 0, ssl=context)
    port = server.sockets[0].getsockname()[1]
    try:
        async with aiohttp.ClientSession() as session:
            client = MeshBeaconClient(session, "127.0.0.1", port, TOKEN, fingerprint)
            return await client.async_get_status(), server_state
    finally:
        server.close()
        await server.wait_closed()


def _body(**changes) -> bytes:
    return json.dumps(snapshot(**changes)).encode()


@pytest.mark.parametrize(("piece", "extra"), [(1, 0), (7, 300), (512, 1500)])
async def test_fragmented_content_length_reply_is_read_completely(tls, piece, extra):
    body = _body(app__message="x" * extra)  # several pieces even at 512 bytes

    async def reply(writer):
        writer.write(_head(len(body)))
        await _pieces(writer, body, piece)

    status, server = await _fetch(tls, reply)
    assert status.message == "x" * extra
    assert status.peers[0].name == "Emerald"
    assert b"accept-encoding: identity" in server.requests[0].lower()


async def test_fragmented_chunked_reply_is_read_completely(tls):
    body = _body()

    async def reply(writer):
        writer.write(_head(None, chunked=True))
        for start in range(0, len(body), 100):
            part = body[start : start + 100]
            await _pieces(writer, f"{len(part):x}\r\n".encode() + part + b"\r\n", 9)
        writer.write(b"0\r\n\r\n")

    status, _ = await _fetch(tls, reply)
    assert status.paths == 42


async def test_reply_without_length_is_read_until_close(tls):
    body = _body()

    async def reply(writer):
        writer.write(_head(None))
        await _pieces(writer, body, 64)

    status, _ = await _fetch(tls, reply)
    assert status.version == "0.2.0"


async def test_exactly_the_limit_is_accepted(tls):
    body = _body()
    body = body[:-1] + b" " * (MAX_RESPONSE - len(body)) + b"}"
    assert len(body) == MAX_RESPONSE

    async def reply(writer):
        writer.write(_head(len(body)))
        await _pieces(writer, body, 16 * 1024)

    status, _ = await _fetch(tls, reply)
    assert status.state == "running"


async def test_declared_oversize_is_refused_before_reading(tls):
    async def reply(writer):
        writer.write(_head(MAX_RESPONSE + 1))
        await _pieces(writer, b"{" * 1024, 1024)

    with pytest.raises(SchemaError, match="too large"):
        await _fetch(tls, reply)


@pytest.mark.parametrize("chunked", [True, False])
async def test_undeclared_oversize_is_refused_while_reading(tls, chunked):
    """No length header (or chunked): the limit still applies, one byte over is enough."""

    async def reply(writer):
        writer.write(_head(None, chunked=chunked))
        piece = b" " * 8192
        for _ in range(MAX_RESPONSE // len(piece) + 1):
            if chunked:
                writer.write(f"{len(piece):x}\r\n".encode() + piece + b"\r\n")
            else:
                writer.write(piece)
            await writer.drain()
        if chunked:
            writer.write(b"0\r\n\r\n")

    with pytest.raises(SchemaError, match="too large"):
        await _fetch(tls, reply)


async def test_truncated_reply_is_a_connection_error_not_partial_data(tls):
    body = _body()

    async def reply(writer):
        writer.write(_head(len(body)))
        await _pieces(writer, body[: len(body) // 2], 50)  # then hang up

    with pytest.raises(MeshBeaconError) as caught:
        await _fetch(tls, reply)
    assert not isinstance(caught.value, SchemaError)


class _Trickle:
    """A StreamReader stand-in that hands out at most ``piece`` bytes per call, like a slow socket."""

    def __init__(self, data: bytes, piece: int) -> None:
        self.data, self.piece, self.asked = data, piece, []

    async def read(self, n: int = -1) -> bytes:
        self.asked.append(n)
        out, self.data = self.data[: min(n, self.piece)], self.data[min(n, self.piece) :]
        return out


@pytest.mark.parametrize(("size", "piece"), [(0, 1), (1, 1), (100, 1), (100, 33), (100, 100), (100, 1000)])
async def test_read_bounded_joins_every_fragment(size, piece):
    data = bytes(range(256)) * (size // 256 + 1)
    data = data[:size]
    assert await read_bounded(_Trickle(data, piece), 100) == data  # type: ignore[arg-type]


async def test_read_bounded_never_asks_for_more_than_one_byte_past_the_limit():
    stream = _Trickle(b"a" * 1000, 30)
    with pytest.raises(SchemaError):
        await read_bounded(stream, 100)  # type: ignore[arg-type]
    assert all(0 < n <= 101 for n in stream.asked)
    assert sum(min(n, 30) for n in stream.asked) <= 101
