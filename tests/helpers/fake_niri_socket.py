"""Centralized fake socket helpers for niri-pypc tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FakeSocketConfig:
    response: bytes | None = None
    bootstrap_reply: dict | None = None
    events: list[dict] = field(default_factory=list)
    received_requests: list[bytes] = field(default_factory=list)
    received_request: bytes | None = None


async def create_command_server(
    response: bytes | None = None,
) -> tuple[Path, FakeSocketConfig]:
    config = FakeSocketConfig(response=response)

    async def handler(reader, writer):
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
    bootstrap_reply: dict | None = None,
) -> tuple[Path, FakeSocketConfig]:
    config = FakeSocketConfig(events=events, bootstrap_reply=bootstrap_reply)

    async def handler(reader, writer):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return
        config.received_request = data

        # Send bootstrap reply first if configured
        if config.bootstrap_reply is not None:
            frame = json.dumps(config.bootstrap_reply).encode() + b"\n"
            writer.write(frame)
            await writer.drain()

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
    cmd_config = FakeSocketConfig(response=response)
    evt_config = FakeSocketConfig(events=events or [])
    connection_count = 0

    async def handler(reader, writer):
        nonlocal connection_count
        connection_count += 1

        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return

        if b"EventStream" in data:
            evt_config.received_request = data
            # Send bootstrap reply
            frame = json.dumps({"Ok": {"Handled": {}}}).encode() + b"\n"
            writer.write(frame)
            await writer.drain()
            # Send events
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
    def __init__(self, socket_path: Path, server: asyncio.Server):
        self.socket_path = socket_path
        self._server = server

    async def __aenter__(self) -> MockServer:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._server.close()
        await self._server.wait_closed()
        self.socket_path.parent.rmdir()
