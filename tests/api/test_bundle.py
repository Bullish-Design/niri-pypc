"""Tests for NiriConnectionBundle."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from niri_pypc.api.bundle import NiriConnectionBundle
from niri_pypc.config import NiriConfig

pytestmark = pytest.mark.contract


@pytest.fixture
async def unified_server():
    """Create a single mock server that handles both command and event flows.

    - First connection: handles a command request (read frame, send response, close).
    - Second connection: handles an event stream (read EventStream, send bootstrap, send events).
    """
    cmd_ctrl = {"response": None, "received_requests": []}
    evt_ctrl = {"events": [], "received_request": None}
    connection_count = 0

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal connection_count
        connection_count += 1

        data = await reader.readuntil(b"\n")

        is_event_stream = b"EventStream" in data

        if is_event_stream:
            evt_ctrl["received_request"] = data
            # Send bootstrap reply
            frame = json.dumps({"Ok": {"Handled": {}}}).encode() + b"\n"
            writer.write(frame)
            await writer.drain()
            # Send events
            for evt in evt_ctrl["events"]:
                frame = json.dumps(evt).encode() + b"\n"
                writer.write(frame)
                await writer.drain()
                await asyncio.sleep(0.01)
            writer.close()
        else:
            cmd_ctrl["received_requests"].append(data)
            if cmd_ctrl["response"] is not None:
                writer.write(cmd_ctrl["response"])
                await writer.drain()
            writer.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "unified.sock"
        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        yield socket_path, cmd_ctrl, evt_ctrl
        server.close()
        await server.wait_closed()


class TestNiriConnectionBundle:
    async def test_open_and_close(self, unified_server):
        """Bundle opens and closes cleanly."""
        socket_path, cmd_ctrl, evt_ctrl = unified_server
        cmd_ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"
        evt_ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        bundle = await NiriConnectionBundle.open(config)

        from niri_pypc.types.generated.request import VersionRequest

        from niri_pypc.types.generated.reply import VersionResponse

        result = await bundle.client.request(VersionRequest())
        assert isinstance(result, VersionResponse)
        assert result.payload == "0.1.0"

        await bundle.close()

    async def test_member_independence(self, unified_server):
        """Event stream EOF does not break the command client."""
        socket_path, cmd_ctrl, evt_ctrl = unified_server
        cmd_ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"
        evt_ctrl["events"] = []

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        bundle = await NiriConnectionBundle.open(config)

        from niri_pypc.types.generated.reply import VersionResponse
        from niri_pypc.types.generated.request import VersionRequest

        result = await bundle.client.request(VersionRequest())
        assert isinstance(result, VersionResponse)
        assert result.payload == "0.1.0"

        await bundle.close()

    async def test_close_is_idempotent(self, unified_server):
        """Bundle close can be called multiple times."""
        socket_path, cmd_ctrl, evt_ctrl = unified_server
        cmd_ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"
        evt_ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        bundle = await NiriConnectionBundle.open(config)
        await bundle.close()
        await bundle.close()

    async def test_async_context_manager(self, unified_server):
        """Bundle works as async context manager."""
        socket_path, cmd_ctrl, evt_ctrl = unified_server
        cmd_ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"
        evt_ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        from niri_pypc.types.generated.request import VersionRequest

        async with await NiriConnectionBundle.open(config) as bundle:
            result = await bundle.client.request(VersionRequest())
            assert result.payload == "0.1.0"

    async def test_client_and_events_properties(self, unified_server):
        """Client and events properties return the correct instances."""
        socket_path, cmd_ctrl, evt_ctrl = unified_server
        cmd_ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"
        evt_ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        bundle = await NiriConnectionBundle.open(config)

        from niri_pypc.api.client import NiriClient
        from niri_pypc.api.event_stream import NiriEventStream

        assert isinstance(bundle.client, NiriClient)
        assert isinstance(bundle.events, NiriEventStream)

        await bundle.close()
