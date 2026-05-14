"""Convenience wrapper for command client and event stream."""

from __future__ import annotations

from typing import Any

from niri_pypc.api.client import NiriClient
from niri_pypc.api.event_stream import NiriEventStream
from niri_pypc.config import NiriConfig


class NiriConnectionBundle:
    """Convenience wrapper holding both a command client and event stream."""

    def __init__(self, client: NiriClient, events: NiriEventStream) -> None:
        self._client = client
        self._events = events
        self._closed = False

    @classmethod
    async def open(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriConnectionBundle:
        """Open both command and event connections."""
        if config is None:
            config = NiriConfig()

        client = NiriClient.create(config)
        try:
            events = await NiriEventStream.connect(config)
        except Exception:
            await client.close()
            raise

        return cls(client, events)

    @property
    def client(self) -> NiriClient:
        return self._client

    @property
    def events(self) -> NiriEventStream:
        return self._events

    async def close(self) -> None:
        """Close both connections. Idempotent."""
        if self._closed:
            return
        self._closed = True

        first_exc = None
        try:
            await self._client.close()
        except Exception as exc:
            first_exc = exc
        try:
            await self._events.close()
        except Exception as exc:
            if first_exc is None:
                first_exc = exc

        if first_exc is not None:
            raise first_exc

    async def __aenter__(self) -> NiriConnectionBundle:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
