"""Event stream client for niri IPC."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from niri_pypc.config import BackpressureMode, NiriConfig
from niri_pypc.errors import InternalError, LifecycleError, TransportError
from niri_pypc.runtime.lifecycle import LifecycleManager, LifecycleState
from niri_pypc.transport.connection import UnixConnection
from niri_pypc.transport.framing import decode_frame, encode_frame
from niri_pypc.types.generated.event import Event


class _StreamClosed(Exception):
    """Internal sentinel: the event stream has been closed."""


class NiriEventStream:
    """Event stream client for niri IPC.

    Opens a single persistent connection, sends an EventStream request,
    and yields decoded events.
    """

    def __init__(self, config: NiriConfig) -> None:
        self._config = config
        self._lifecycle = LifecycleManager()
        self._queue: asyncio.Queue[BaseModel | _StreamClosed] | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._connection: UnixConnection | None = None

    @classmethod
    async def connect(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriEventStream:
        """Connect to the niri event socket.

        Flow:
        1. Resolve socket path.
        2. Open UnixConnection.
        3. Send EventStream request frame.
        4. Transition to READY.
        5. Start background reader task that decodes events into the queue.
        """
        if config is None:
            config = NiriConfig()

        instance = cls(config)
        mgr = instance._lifecycle

        await mgr.transition_to(LifecycleState.CONNECTING)

        socket_path = config.resolve_socket_path()
        conn = await UnixConnection.connect(
            socket_path,
            timeout=config.connect_timeout,
        )
        instance._connection = conn

        from niri_pypc.types.generated.request import EventStreamRequest
        from niri_pypc.types.generated.request import Request as RequestModel

        request_root = RequestModel(variant=EventStreamRequest())
        payload = request_root.model_dump(mode="json")
        frame = encode_frame(payload)
        await conn.write_frame(frame)

        instance._queue = asyncio.Queue(maxsize=config.event_queue_capacity)
        instance._reader_task = asyncio.create_task(
            instance._run_reader(),
        )

        await mgr.transition_to(LifecycleState.READY)
        return instance

    async def _run_reader(self) -> None:
        """Background task: read frames, decode Events, push to queue."""
        conn = self._connection
        queue = self._queue
        config = self._config
        if conn is None or queue is None:
            return

        try:
            while True:
                try:
                    raw = await conn.read_frame(
                        max_size=config.max_frame_size,
                        timeout=config.event_read_timeout,
                    )
                except TransportError:
                    break

                try:
                    decoded = decode_frame(raw)
                    event = Event.model_validate(decoded)
                except Exception:
                    # Malformed event — skip it
                    continue

                if config.backpressure_mode == BackpressureMode.DROP_OLDEST:
                    try:
                        queue.put_nowait(event.variant)
                    except asyncio.QueueFull:
                        try:
                            queue.get_nowait()
                            queue.put_nowait(event.variant)
                        except asyncio.QueueEmpty:
                            pass
                else:
                    try:
                        queue.put_nowait(event.variant)
                    except asyncio.QueueFull:
                        # FAIL_FAST: drop event and signal backpressure
                        await self._close_from_reader()
                        return
        except Exception:
            pass
        finally:
            await self._close_from_reader()

    async def _close_from_reader(self) -> None:
        """Close the stream from the reader task context."""
        if self._lifecycle.is_terminal:
            return
        await self._lifecycle.transition_to(LifecycleState.CLOSING)
        if self._queue is not None:
            self._queue.put_nowait(_StreamClosed())
        self._connection = None
        await self._lifecycle.transition_to(LifecycleState.CLOSED)

    async def next(self, *, timeout: float | None = None) -> BaseModel:
        """Read the next event from the stream.

        Args:
            timeout: Seconds to wait. None uses config.event_read_timeout.

        Returns:
            A decoded event variant model instance.

        Raises:
            NiriTimeoutError: If timeout expires with no event.
            TransportError: If the connection has been lost.
            LifecycleError: If the stream has been closed.
        """
        if self._lifecycle.is_terminal:
            raise LifecycleError(
                "Event stream is closed",
                operation="next",
                state=self._lifecycle.state.value,
            )
        if self._queue is None:
            raise InternalError(
                "Event stream not connected",
                operation="next",
            )

        try:
            read_timeout = timeout if timeout is not None else self._config.event_read_timeout
            event = await asyncio.wait_for(self._queue.get(), timeout=read_timeout)
        except TimeoutError:
            from niri_pypc.errors import NiriTimeoutError

            raise NiriTimeoutError(
                "No event received within timeout",
                operation="next",
                retryable=True,
            ) from None

        if isinstance(event, _StreamClosed):
            raise LifecycleError(
                "Event stream has been closed",
                operation="next",
                state=self._lifecycle.state.value,
            )

        return event

    def __aiter__(self) -> AsyncIterator[BaseModel]:
        return self._async_iterator()

    async def _async_iterator(self) -> AsyncIterator[BaseModel]:
        while True:
            try:
                yield await self.next()
            except LifecycleError:
                break

    async def __anext__(self) -> BaseModel:
        event = await self.next()
        return event

    async def close(self) -> None:
        """Close the event stream. Idempotent."""
        if self._lifecycle.is_terminal:
            return
        await self._lifecycle.transition_to(LifecycleState.CLOSING)
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None
        if self._queue is not None:
            self._queue.put_nowait(_StreamClosed())
        await self._lifecycle.transition_to(LifecycleState.CLOSED)

    async def __aenter__(self) -> NiriEventStream:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
