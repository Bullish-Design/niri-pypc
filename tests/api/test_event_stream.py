"""Tests for NiriEventStream."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from niri_pypc.api.event_stream import NiriEventStream
from niri_pypc.config import BackpressureMode, NiriConfig
from niri_pypc.errors import DecodeError, LifecycleError, ProtocolError, TransportError

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
        assert ctrl["received_request"] == b'"EventStream"\n'
        assert not ctrl["received_request"].endswith(b"\n\n")

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
    async def test_fail_fast_queue_pressure_raises_protocol_error(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = [{"WorkspaceActivated": {"id": i, "focused": i % 2 == 0}} for i in range(1, 200)]
        config = NiriConfig(
            socket_path=socket_path,
            event_queue_capacity=1,
            backpressure_mode=BackpressureMode.FAIL_FAST,
        )
        stream = await NiriEventStream.connect(config)
        await asyncio.sleep(0.05)
        with pytest.raises(ProtocolError, match="Event queue full \\(FAIL_FAST mode\\)"):
            await stream.next(timeout=1.0)
        await stream.close()

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

    async def test_anext_after_close_stops_iteration(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = []
        stream = await NiriEventStream.connect(NiriConfig(socket_path=socket_path))
        await stream.close()
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    async def test_terminal_event_unblocks_next_when_terminal_enqueue_is_dropped(self, event_server):
        socket_path, ctrl = event_server
        ctrl["events"] = []
        stream = await NiriEventStream.connect(NiriConfig(socket_path=socket_path))
        stream._enqueue_terminal = lambda item: None  # type: ignore[method-assign]
        terminal = ProtocolError("forced terminal", operation="test")
        stream._signal_terminal(terminal)
        with pytest.raises(ProtocolError, match="forced terminal"):
            await stream.next(timeout=0.1)
        await stream.close()

    async def test_direct_next_surfaces_decode_error(self):
        async def handler(reader, writer):
            await reader.readuntil(b"\n")
            writer.write(json.dumps({"Ok": {"Handled": {}}}).encode() + b"\n")
            await writer.drain()
            writer.write(b"{not-json}\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = Path(tmpdir) / "event.sock"
            server = await asyncio.start_unix_server(handler, path=str(socket_path))
            try:
                stream = await NiriEventStream.connect(NiriConfig(socket_path=socket_path))
                with pytest.raises(DecodeError, match="Failed to decode event"):
                    await stream.next(timeout=1.0)
            finally:
                server.close()
                await server.wait_closed()

    async def test_bootstrap_failure_closes_connection(self):
        async def handler(reader, writer):
            await reader.readuntil(b"\n")
            writer.write(json.dumps({"Ok": {"Version": "25.11"}}).encode() + b"\n")
            await writer.drain()
            await asyncio.sleep(0.05)
            writer.close()
            await writer.wait_closed()

        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = Path(tmpdir) / "event.sock"
            server = await asyncio.start_unix_server(handler, path=str(socket_path))
            try:
                with pytest.raises(ProtocolError):
                    await NiriEventStream.connect(NiriConfig(socket_path=socket_path))
            finally:
                server.close()
                await server.wait_closed()

    async def test_connect_handles_immediate_post_bootstrap_close(self):
        async def handler(reader, writer):
            await reader.readuntil(b"\n")
            writer.write(json.dumps({"Ok": {"Handled": {}}}).encode() + b"\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = Path(tmpdir) / "event.sock"
            server = await asyncio.start_unix_server(handler, path=str(socket_path))
            try:
                stream = await NiriEventStream.connect(NiriConfig(socket_path=socket_path))
                with pytest.raises(TransportError):
                    await stream.next(timeout=1.0)
            finally:
                server.close()
                await server.wait_closed()

    async def test_oversized_event_preserves_protocol_error(self):
        async def handler(reader, writer):
            await reader.readuntil(b"\n")
            writer.write(json.dumps({"Ok": {"Handled": {}}}).encode() + b"\n")
            await writer.drain()
            writer.write(b"x" * 2000 + b"\n")
            await writer.drain()
            await asyncio.sleep(0.05)
            writer.close()
            await writer.wait_closed()

        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = Path(tmpdir) / "event.sock"
            server = await asyncio.start_unix_server(handler, path=str(socket_path))
            try:
                stream = await NiriEventStream.connect(
                    NiriConfig(socket_path=socket_path, max_frame_size=100),
                )
                with pytest.raises(ProtocolError):
                    await stream.next(timeout=1.0)
            finally:
                server.close()
                await server.wait_closed()
