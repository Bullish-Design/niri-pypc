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

pytestmark = pytest.mark.contract


@pytest.fixture
async def mock_server():
    server_control = {"response": None, "received_requests": []}

    async def handler(reader, writer):
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
    async def test_create_and_connect_are_compatible(self, mock_server):
        socket_path, _ = mock_server
        config = NiriConfig(socket_path=socket_path)
        via_create = NiriClient.create(config)
        via_connect = NiriClient.connect(config)
        assert isinstance(via_create, NiriClient)
        assert isinstance(via_connect, NiriClient)
        assert via_create._config == via_connect._config

    async def test_request_returns_decoded_reply(self, mock_server):
        socket_path, ctrl = mock_server
        ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        async with NiriClient.create(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            result = await client.request(VersionRequest())

        from niri_pypc.types.generated.reply import VersionResponse

        assert isinstance(result, VersionResponse)
        assert result.payload == "0.1.0"

    async def test_request_sends_correct_frame(self, mock_server):
        socket_path, ctrl = mock_server
        ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        async with NiriClient.create(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            await client.request(VersionRequest())

        assert len(ctrl["received_requests"]) == 1
        assert ctrl["received_requests"][0] == b'"Version"\n'
        assert not ctrl["received_requests"][0].endswith(b"\n\n")

    async def test_action_serializes_as_zero_field_struct(self, mock_server):
        socket_path, ctrl = mock_server
        ctrl["response"] = json.dumps({"Ok": {"Handled": {}}}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        async with NiriClient.create(config) as client:
            from niri_pypc.types.generated.action import Action, ToggleOverviewAction
            from niri_pypc.types.generated.request import ActionRequest

            await client.request(ActionRequest(payload=Action(root=ToggleOverviewAction())))

        assert ctrl["received_requests"][0] == b'{"Action":{"ToggleOverview":{}}}\n'

    async def test_request_handles_err_response(self, mock_server):
        socket_path, ctrl = mock_server
        ctrl["response"] = json.dumps({"Err": "Something went wrong"}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        async with NiriClient.create(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            with pytest.raises(RemoteError, match="Compositor error"):
                await client.request(VersionRequest())

    async def test_close_client_rejects_requests(self, mock_server):
        socket_path, ctrl = mock_server
        config = NiriConfig(socket_path=socket_path)

        client = NiriClient.create(config)
        await client.close()
        from niri_pypc.errors import LifecycleError
        from niri_pypc.types.generated.request import VersionRequest

        with pytest.raises(LifecycleError, match="Client is closed"):
            await client.request(VersionRequest())

    async def test_request_timeout_on_no_response(self, mock_server):
        socket_path, ctrl = mock_server
        ctrl["response"] = None

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=0.1)
        async with NiriClient.create(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            with pytest.raises(TransportError):
                await client.request(VersionRequest())

    async def test_async_context_manager(self, mock_server):
        socket_path, ctrl = mock_server
        ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        from niri_pypc.types.generated.request import VersionRequest

        async with NiriClient.create(config) as client:
            result = await client.request(VersionRequest())
            assert result.payload == "0.1.0"
        assert client.is_closed

    async def test_request_accepts_large_frame_within_max_size(self, mock_server):
        socket_path, ctrl = mock_server
        payload = "x" * 70000
        ctrl["response"] = json.dumps({"Ok": {"Version": payload}}).encode() + b"\n"

        config = NiriConfig(
            socket_path=socket_path,
            connect_timeout=5.0,
            request_timeout=5.0,
            max_frame_size=200000,
        )
        async with NiriClient.create(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            result = await client.request(VersionRequest())

        assert result.payload == payload

    async def test_request_rejects_large_frame_over_max_size(self, mock_server):
        socket_path, ctrl = mock_server
        payload = "x" * 70000
        ctrl["response"] = json.dumps({"Ok": {"Version": payload}}).encode() + b"\n"

        config = NiriConfig(
            socket_path=socket_path,
            connect_timeout=5.0,
            request_timeout=5.0,
            max_frame_size=1024,
        )
        async with NiriClient.create(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            with pytest.raises(ProtocolError, match="Frame exceeds maximum"):
                await client.request(VersionRequest())

    async def test_request_reports_connect_failure_with_operation_context(self):
        config = NiriConfig(socket_path=Path("/tmp/does-not-exist-niri.sock"), connect_timeout=0.1)
        client = NiriClient.create(config)
        from niri_pypc.types.generated.request import VersionRequest

        with pytest.raises(TransportError) as exc_info:
            await client.request(VersionRequest())
        assert exc_info.value.operation == "connect"
