"""Centralized fake socket helpers for niri-pypc tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FakeSocketConfig:
    """Configuration for fake socket server behavior."""

    response: bytes | None = None
    events: list[dict] = field(default_factory=list)
    received_requests: list[bytes] = field(default_factory=list)
    received_request: bytes | None = None


async def create_command_server(
    response: bytes | None = None,
) -> tuple[Path, FakeSocketConfig]:
    """Create a mock Unix socket server for command-mode testing.

    Args:
        response: Bytes to send back as response (or None to close without response)

    Returns:
        Tuple of (socket_path, control_config)
    """
    config = FakeSocketConfig(response=response)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return
        config.received_requests.append(data)
        if config.response is not None:
            writer.write(config.response)
            await writer.drain()
        writer.close()

    tmpdir = Path("/tmp") / f"fake_cmd_{id(config)}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    socket_path = tmpdir / "cmd.sock"
    await asyncio.start_unix_server(handler, path=str(socket_path))
    return socket_path, config


async def create_event_server(
    events: list[dict],
) -> tuple[Path, FakeSocketConfig]:
    """Create a mock Unix socket server for event-stream testing.

    Args:
        events: List of event dicts to send to the client

    Returns:
        Tuple of (socket_path, control_config)
    """
    config = FakeSocketConfig(events=events)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return
        config.received_request = data
        for evt in config.events:
            frame = json.dumps(evt).encode() + b"\n"
            writer.write(frame)
            await writer.drain()
            await asyncio.sleep(0.01)
        writer.close()

    tmpdir = Path("/tmp") / f"fake_evt_{id(config)}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    socket_path = tmpdir / "evt.sock"
    await asyncio.start_unix_server(handler, path=str(socket_path))
    return socket_path, config


async def create_unified_server(
    response: bytes | None = None,
    events: list[dict] | None = None,
) -> tuple[Path, FakeSocketConfig, FakeSocketConfig]:
    """Create a single mock server handling both command and event flows.

    First connection handles EventStream request (event mode).
    Subsequent connections handle command requests.

    Args:
        response: Bytes to send back for command requests
        events: List of event dicts to send for event stream

    Returns:
        Tuple of (socket_path, cmd_control, evt_control)
    """
    cmd_config = FakeSocketConfig(response=response)
    evt_config = FakeSocketConfig(events=events or [])
    connection_count = 0

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal connection_count
        connection_count += 1

        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return

        if b"EventStream" in data:
            evt_config.received_request = data
            for evt in evt_config.events:
                frame = json.dumps(evt).encode() + b"\n"
                writer.write(frame)
                await writer.drain()
                await asyncio.sleep(0.01)
            writer.close()
        else:
            cmd_config.received_requests.append(data)
            if cmd_config.response is not None:
                writer.write(cmd_config.response)
                await writer.drain()
            writer.close()

    tmpdir = Path("/tmp") / f"fake_unified_{id(connection_count)}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    socket_path = tmpdir / "unified.sock"
    await asyncio.start_unix_server(handler, path=str(socket_path))
    return socket_path, cmd_config, evt_config


class MockServer:
    """Context manager for mock socket server lifecycle."""

    def __init__(self, socket_path: Path, server: asyncio.Server):
        self.socket_path = socket_path
        self._server = server

    async def __aenter__(self) -> MockServer:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._server.close()
        await self._server.wait_closed()
        self.socket_path.parent.rmdir()
