"""Tests for NiriClient."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from niri_pypc.api.client import NiriClient
from niri_pypc.config import NiriConfig
from niri_pypc.errors import ProtocolError, RemoteError, TransportError


@pytest.fixture
async def mock_server():
    """Create a mock niri command server.

    Accepts one connection, reads a request frame, sends a canned response,
    then closes.
    """
    server_control = {"response": None, "received_requests": []}

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        data = await reader.readuntil(b"\n")
        server_control["received_requests"].append(data)
        if server_control["response"] is not None:
            writer.write(server_control["response"])
            await writer.drain()
        writer.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        yield socket_path, server_control
        server.close()
        await server.wait_closed()


class TestNiriClient:
    async def test_request_returns_decoded_reply(self, mock_server):
        """Client.request() returns the decoded Ok payload."""
        socket_path, ctrl = mock_server
        # The proper wire format is {"Ok": {"Version": "0.1.0"}}
        ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        async with NiriClient.connect(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            result = await client.request(VersionRequest())

        # Result should be a Response model whose variant is VersionResponse
        assert result.variant.payload == "0.1.0"

    async def test_request_sends_correct_frame(self, mock_server):
        """Client sends the correct serialized request frame."""
        socket_path, ctrl = mock_server
        ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        async with NiriClient.connect(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            await client.request(VersionRequest())

        assert len(ctrl["received_requests"]) == 1
        # VersionRequest is a unit variant, should serialize to "Version\n"
        assert ctrl["received_requests"][0] == b'"Version"\n'

    async def test_request_handles_err_response(self, mock_server):
        """Err response raises RemoteError."""
        socket_path, ctrl = mock_server
        ctrl["response"] = json.dumps({"Err": "Something went wrong"}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        async with NiriClient.connect(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            with pytest.raises(RemoteError, match="Compositor error"):
                await client.request(VersionRequest())

    async def test_close_client_rejects_requests(self, mock_server):
        """After close, requests raise LifecycleError."""
        socket_path, ctrl = mock_server
        config = NiriConfig(socket_path=socket_path)

        client = NiriClient.connect(config)
        await client.close()
        from niri_pypc.errors import LifecycleError
        from niri_pypc.types.generated.request import VersionRequest

        with pytest.raises(LifecycleError, match="Client is closed"):
            await client.request(VersionRequest())

    async def test_request_timeout_on_no_response(self, mock_server):
        """If server doesn't respond, request times out."""
        socket_path, ctrl = mock_server
        # Don't set a response - the server will close without responding
        # This will cause a read error/EOF rather than a timeout
        ctrl["response"] = None

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=0.1)
        async with NiriClient.connect(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            with pytest.raises(TransportError):
                await client.request(VersionRequest())

    async def test_async_context_manager(self, mock_server):
        """Async context manager works correctly."""
        socket_path, ctrl = mock_server
        ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        from niri_pypc.types.generated.request import VersionRequest

        async with NiriClient.connect(config) as client:
            result = await client.request(VersionRequest())
            assert result.variant.payload == "0.1.0"
        # After context manager exit, client should be closed
        assert client.is_closed

    async def test_request_accepts_large_frame_within_max_size(self, mock_server):
        """Large frames above asyncio defaults are accepted when under max_frame_size."""
        socket_path, ctrl = mock_server
        payload = "x" * 70000
        ctrl["response"] = json.dumps({"Ok": {"Version": payload}}).encode() + b"\n"

        config = NiriConfig(
            socket_path=socket_path,
            connect_timeout=5.0,
            request_timeout=5.0,
            max_frame_size=200000,
        )
        async with NiriClient.connect(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            result = await client.request(VersionRequest())

        assert result.variant.payload == payload

    async def test_request_rejects_large_frame_over_max_size(self, mock_server):
        """Frames over configured max_frame_size raise ProtocolError."""
        socket_path, ctrl = mock_server
        payload = "x" * 70000
        ctrl["response"] = json.dumps({"Ok": {"Version": payload}}).encode() + b"\n"

        config = NiriConfig(
            socket_path=socket_path,
            connect_timeout=5.0,
            request_timeout=5.0,
            max_frame_size=1024,
        )
        async with NiriClient.connect(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            with pytest.raises(ProtocolError, match="Frame exceeds maximum"):
                await client.request(VersionRequest())
