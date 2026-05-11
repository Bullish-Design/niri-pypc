"""Convenience wrapper for command client and event stream."""

from __future__ import annotations

from typing import Any

from niri_pypc.api.client import NiriClient
from niri_pypc.api.event_stream import NiriEventStream
from niri_pypc.config import NiriConfig
from niri_pypc.runtime.lifecycle import LifecycleManager, LifecycleState


class NiriConnectionBundle:
    """Convenience wrapper holding both a command client and event stream.

    Lifetime semantics:
    - Closing the bundle closes both members.
    - Members have independent error isolation: one failing does not
      force-close the other.
    - Access members via .client and .events properties.
    """

    def __init__(self, client: NiriClient, events: NiriEventStream) -> None:
        self._client = client
        self._events = events
        self._lifecycle = LifecycleManager()
        self._lifecycle._state = LifecycleState.READY  # skip to ready

    @classmethod
    async def open(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriConnectionBundle:
        """Open both command and event connections.

        If event stream connection fails after client succeeds,
        the client is closed before raising.
        """
        if config is None:
            config = NiriConfig()

        client = NiriClient.connect(config)
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
        """Close both connections. Idempotent.

        Closes both members, suppressing secondary close errors.
        """
        if self._lifecycle.is_terminal:
            return
        await self._lifecycle.transition_to(LifecycleState.CLOSING)

        exc_caught = None
        try:
            await self._client.close()
        except Exception as exc:
            exc_caught = exc
        try:
            await self._events.close()
        except Exception as exc:
            if exc_caught is None:
                exc_caught = exc

        await self._lifecycle.transition_to(LifecycleState.CLOSED)

        if exc_caught is not None:
            raise exc_caught  # noqa: TRY201

    async def __aenter__(self) -> NiriConnectionBundle:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
