"""Integration tests for command request/response flow."""

from __future__ import annotations

import json

import pytest

from niri_pypc.api.client import NiriClient
from niri_pypc.config import NiriConfig

pytestmark = pytest.mark.contract


class TestCommandFlow:
    async def test_version_request_flow(self, mock_command_server):
        socket_path, ctrl = mock_command_server
        ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        from niri_pypc.types.generated.request import VersionRequest

        async with NiriClient.connect(config) as client:
            result = await client.request(VersionRequest())

        from niri_pypc.types.generated.reply import VersionResponse

        assert isinstance(result, VersionResponse)
        assert result.payload == "0.1.0"

    async def test_multiple_requests_work(self, mock_command_server):
        socket_path, ctrl = mock_command_server
        ctrl["response"] = json.dumps({"Ok": {"Version": "0.1.0"}}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        from niri_pypc.types.generated.request import VersionRequest

        async with NiriClient.connect(config) as client:
            r1 = await client.request(VersionRequest())
            assert r1.payload == "0.1.0"
            r2 = await client.request(VersionRequest())
            assert r2.payload == "0.1.0"

        assert len(ctrl["received_requests"]) == 2

    async def test_err_response_flow(self, mock_command_server):
        socket_path, ctrl = mock_command_server
        ctrl["response"] = json.dumps({"Err": "command failed"}).encode() + b"\n"

        config = NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0)
        from niri_pypc.errors import RemoteError
        from niri_pypc.types.generated.request import VersionRequest

        async with NiriClient.connect(config) as client:
            with pytest.raises(RemoteError, match="command failed"):
                await client.request(VersionRequest())
