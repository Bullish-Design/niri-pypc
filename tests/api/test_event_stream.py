"""Tests for NiriEventStream."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from niri_pypc.api.event_stream import NiriEventStream
from niri_pypc.config import NiriConfig
from niri_pypc.errors import LifecycleError, ProtocolError, RemoteError

pytestmark = pytest.mark.contract


@pytest.fixture
async def event_server():
    server_control = {"events": [], "received_request": None, "close_on_connect": False}

    async def handler(reader, writer):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=5.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return
        server_control["received_request"] = data

        if server_control.get("close_on_connect"):
            writer.close()
            return

        # Send bootstrap reply
        frame = json.dumps({"Ok": {"Handled": {}}}).encode() + b"\n"
        writer.write(frame)
        await writer.drain()

        for evt in server_control["events"]:
            frame = json.dumps(evt).encode() + b"\n"
            writer.write(frame)
            await writer.drain()
            await asyncio.sleep(0.01)
        writer.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "event.sock"
        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        yield socket_path, server_control
        server.close()
        await server.wait_closed()


class TestNiriEventStream:
    async def test_stream_yields_events(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [
            {"WorkspaceActivated": {"id": 1, "focused": True}},
            {"WorkspaceActivated": {"id": 2, "focused": False}},
        ]

        config = NiriConfig(socket_path=socket_path)
        stream = await NiriEventStream.connect(config)
        e1 = await stream.next(timeout=1.0)
        assert e1.id == 1
        assert e1.focused is True

        e2 = await stream.next(timeout=1.0)
        assert e2.id == 2
        assert e2.focused is False

        await stream.close()

    async def test_stream_receives_eventstream_request(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path)
        stream = await NiriEventStream.connect(config)
        await stream.next(timeout=1.0)
        await stream.close()

        assert ctrl["received_request"] is not None
        assert b"EventStream" in ctrl["received_request"]

    async def test_close_is_idempotent(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path)
        stream = await NiriEventStream.connect(config)
        await stream.close()
        await stream.close()
        assert stream._lifecycle.is_terminal

    async def test_next_after_close_raises(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path)
        stream = await NiriEventStream.connect(config)
        await stream.close()
        with pytest.raises(LifecycleError, match="Event stream is closed"):
            await stream.next(timeout=1.0)

    async def test_async_iterator(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [
            {"WorkspaceActivated": {"id": 1, "focused": True}},
            {"WorkspaceActivated": {"id": 2, "focused": False}},
        ]

        config = NiriConfig(socket_path=socket_path)
        stream = await NiriEventStream.connect(config)

        events = []
        async for event in stream:
            events.append((event.id, event.focused))
            if len(events) == 2:
                break

        assert events == [(1, True), (2, False)]

    async def test_async_context_manager(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path)
        async with await NiriEventStream.connect(config) as stream:
            event = await stream.next(timeout=1.0)
            assert event.id == 1

        assert stream._lifecycle.is_terminal

    async def test_unknown_event_does_not_crash(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [
            {"UnknownFutureEvent": {"some": "data"}},
            {"WorkspaceActivated": {"id": 3, "focused": True}},
        ]

        config = NiriConfig(socket_path=socket_path)
        stream = await NiriEventStream.connect(config)
        e1 = await stream.next(timeout=1.0)
        from niri_pypc.types.base import UnknownEvent

        assert isinstance(e1, UnknownEvent)
        assert e1.variant_name == "UnknownFutureEvent"

        e2 = await stream.next(timeout=1.0)
        assert e2.id == 3

        await stream.close()

    async def test_handshake_consumed_before_first_event(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path)
        stream = await NiriEventStream.connect(config)
        event = await stream.next(timeout=1.0)

        assert event.id == 1
        assert event.focused is True

    async def test_bootstrap_consumed_before_first_event(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path)
        stream = await NiriEventStream.connect(config)
        event = await stream.next(timeout=1.0)

        assert event.id == 1
        assert event.focused is True


class TestEventStreamEdgeCases:
    async def test_close_with_full_queue_does_not_raise(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [{"WorkspaceActivated": {"id": i, "focused": i % 2 == 0}} for i in range(1, 50)]
        config = NiriConfig(
            socket_path=socket_path,
            event_queue_capacity=1,
        )
        stream = await NiriEventStream.connect(config)
        await asyncio.sleep(0.1)
        await stream.close()

    async def test_async_for_stops_on_close(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [{"WorkspaceActivated": {"id": i, "focused": i % 2 == 0}} for i in range(1, 50)]

        config = NiriConfig(socket_path=socket_path)
        stream = await NiriEventStream.connect(config)
        events = []

        async def collect():
            async for event in stream:
                events.append(event)

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.02)
        await stream.close()
        await task
