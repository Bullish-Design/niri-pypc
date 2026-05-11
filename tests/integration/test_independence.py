"""Integration tests for command/event independence."""

from __future__ import annotations

import json

from niri_pypc.api.bundle import NiriConnectionBundle
from niri_pypc.config import NiriConfig


class TestCommandEventIndependence:
    async def test_command_and_event_independence(self, mock_unified_server):
        """Command client works even when event stream is closed."""
        socket_path, cmd_ctrl, evt_ctrl = mock_unified_server
        cmd_ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"
        evt_ctrl["events"] = []

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        bundle = await NiriConnectionBundle.open(config)

        from niri_pypc.types.generated.request import VersionRequest

        result = await bundle.client.request(VersionRequest())
        assert result.variant.payload == "0.1.0"

        await bundle.close()

    async def test_events_received_after_command(self, mock_unified_server):
        """Events can be received after commands (separate connections)."""
        socket_path, cmd_ctrl, evt_ctrl = mock_unified_server
        cmd_ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"
        evt_ctrl["events"] = [
            {"WorkspaceActivated": {"id": 42, "focused": True}},
        ]

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        bundle = await NiriConnectionBundle.open(config)

        from niri_pypc.types.generated.request import VersionRequest

        result = await bundle.client.request(VersionRequest())
        assert result.variant.payload == "0.1.0"

        event = await bundle.events.next(timeout=1.0)
        assert event.id == 42

        await bundle.close()
