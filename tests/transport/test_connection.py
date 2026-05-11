"""Tests for Unix connection transport."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from niri_pypc.errors import NiriTimeoutError, ProtocolError, TransportError
from niri_pypc.transport.connection import UnixConnection


@pytest.fixture
async def socket_path():
    """Provide a temporary socket path (does not create the socket)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.sock"


@pytest.fixture
async def mock_server(socket_path):
    """Create a mock Unix socket server for testing.

    Yields (socket_path, queue) where queue receives received data bytes.
    The server accepts one connection, reads one frame, and sends back a response.
    """

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        data = await reader.readuntil(b"\n")
        await queue.put(data)
        response = json.dumps({"Ok": "pong"}).encode() + b"\n"
        writer.write(response)
        await writer.drain()
        writer.close()

    queue: asyncio.Queue[bytes] = asyncio.Queue()
    server = await asyncio.start_unix_server(handler, path=str(socket_path))

    try:
        yield socket_path, queue
    finally:
        server.close()
        await server.wait_closed()


class TestUnixConnectionConnect:
    async def test_connect_to_nonexistent_socket(self, socket_path):
        with pytest.raises(TransportError, match="Failed to connect"):
            await UnixConnection.connect(socket_path, timeout=1.0)

    async def test_connect_success(self, mock_server):
        sp, _ = mock_server
        conn = await UnixConnection.connect(sp, timeout=5.0)
        assert not conn.is_closed
        await conn.close()
        assert conn.is_closed

    async def test_connect_timeout(self, socket_path):
        """Connect to non-existent socket raises TransportError immediately."""
        with pytest.raises(TransportError, match="Failed to connect"):
            await UnixConnection.connect(socket_path, timeout=0.001)


class TestUnixConnectionWriteRead:
    async def test_write_then_read(self, mock_server):
        sp, queue = mock_server
        conn = await UnixConnection.connect(sp, timeout=5.0)
        await conn.write_frame(b'"ping"\n')
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received == b'"ping"\n'
        response = await conn.read_frame(timeout=1.0)
        assert response == json.dumps({"Ok": "pong"}).encode()
        await conn.close()

    async def test_read_timeout(self, mock_server):
        sp, _ = mock_server
        conn = await UnixConnection.connect(sp, timeout=5.0)
        # Don't write anything, so read will hang
        with pytest.raises(NiriTimeoutError, match="timed out"):
            await conn.read_frame(timeout=0.05)
        await conn.close()

    async def test_oversize_frame_rejected(self, socket_path):
        """Frames exceeding max_size raise ProtocolError."""

        async def handler(reader, writer):
            # Send an oversized frame
            writer.write(b"x" * 101 + b"\n")
            await writer.drain()
            writer.close()

        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        conn = await UnixConnection.connect(socket_path, timeout=5.0)
        with pytest.raises(ProtocolError, match="exceeds maximum"):
            await conn.read_frame(max_size=100, timeout=1.0)
        await conn.close()
        server.close()
        await server.wait_closed()

    async def test_eof_raises_transport_error(self, socket_path):
        """Server closes immediately without sending data."""

        async def handler(reader, writer):
            writer.close()

        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        conn = await UnixConnection.connect(socket_path, timeout=5.0)
        with pytest.raises(TransportError, match="Connection closed"):
            await conn.read_frame(timeout=1.0)
        await conn.close()
        server.close()
        await server.wait_closed()


class TestUnixConnectionClose:
    async def test_close_is_idempotent(self, mock_server):
        sp, _ = mock_server
        conn = await UnixConnection.connect(sp, timeout=5.0)
        await conn.close()
        assert conn.is_closed
        await conn.close()  # second close should not raise
        assert conn.is_closed

    async def test_write_after_close_raises(self, mock_server):
        sp, _ = mock_server
        conn = await UnixConnection.connect(sp, timeout=5.0)
        await conn.close()
        with pytest.raises(TransportError, match="Cannot write to closed"):
            await conn.write_frame(b"data\n")

    async def test_read_after_close_raises(self, mock_server):
        sp, _ = mock_server
        conn = await UnixConnection.connect(sp, timeout=5.0)
        await conn.close()
        with pytest.raises(TransportError, match="Cannot read from closed"):
            await conn.read_frame(timeout=1.0)
