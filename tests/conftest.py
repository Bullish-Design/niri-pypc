"""Shared test fixtures for niri-pypc."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
async def temp_socket_path():
    """Provide a temporary socket path (does not create the socket)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.sock"


@pytest.fixture
async def mock_command_server():
    """Create a mock Unix socket server for command-mode testing.

    Accepts one connection, reads a request frame, sends a canned response,
    then closes. Yields (socket_path, control_dict) where control_dict has:
    - response: bytes to send back (or None to close without response)
    - received_requests: list of received frame bytes
    """
    ctrl = {"response": None, "received_requests": []}

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError):
            writer.close()
            return
        ctrl["received_requests"].append(data)
        if ctrl["response"] is not None:
            writer.write(ctrl["response"])
            await writer.drain()
        writer.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "cmd.sock"
        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        yield socket_path, ctrl
        server.close()
        await server.wait_closed()


@pytest.fixture
async def mock_event_server():
    """Create a mock Unix socket server for event-stream testing.

    Accepts one connection, reads the EventStream request, then sends
    configured event frames and closes. Yields (socket_path, control_dict)
    where control_dict has:
    - events: list of event dicts to send
    - received_request: received request frame bytes
    """
    ctrl = {"events": [], "received_request": None}

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError):
            writer.close()
            return
        ctrl["received_request"] = data
        for evt in ctrl["events"]:
            frame = json.dumps(evt).encode() + b"\n"
            writer.write(frame)
            await writer.drain()
            await asyncio.sleep(0.01)
        writer.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "evt.sock"
        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        yield socket_path, ctrl
        server.close()
        await server.wait_closed()


@pytest.fixture
async def mock_unified_server():
    """Create a single mock server handling both command and event flows.

    The first connection handles an EventStream request (event mode).
    Subsequent connections handle command requests.

    Yields (socket_path, cmd_ctrl, evt_ctrl).
    """
    cmd_ctrl = {"response": None, "received_requests": []}
    evt_ctrl = {"events": [], "received_request": None}
    connection_count = 0

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal connection_count
        connection_count += 1

        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError):
            writer.close()
            return

        if b"EventStream" in data:
            evt_ctrl["received_request"] = data
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
