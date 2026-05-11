"""Integration tests for event subscription flow."""

from __future__ import annotations

from niri_pypc.api.event_stream import NiriEventStream
from niri_pypc.config import NiriConfig


class TestEventFlow:
    async def test_event_subscription_flow(self, mock_event_server):
        """Full event flow: connect, receive events, close."""
        socket_path, ctrl = mock_event_server
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

    async def test_async_iteration_over_events(self, mock_event_server):
        """Events can be consumed via async iteration."""
        socket_path, ctrl = mock_event_server
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

        assert len(events) == 2
        assert events == [(1, True), (2, False)]
        await stream.close()

    async def test_event_stream_sends_request(self, mock_event_server):
        """Stream sends an EventStream request frame on connect."""
        socket_path, ctrl = mock_event_server
        ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

        config = NiriConfig(socket_path=socket_path)
        stream = await NiriEventStream.connect(config)
        await stream.next(timeout=1.0)
        await stream.close()

        assert ctrl["received_request"] is not None
        assert b"EventStream" in ctrl["received_request"]
