"""Event stream client for niri IPC."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from niri_pypc.config import BackpressureMode, NiriConfig
from niri_pypc.errors import (
    DecodeError,
    InternalError,
    LifecycleError,
    NiriTimeoutError,
    ProtocolError,
    TransportError,
)
from niri_pypc.runtime.lifecycle import LifecycleManager, LifecycleState
from niri_pypc.transport.connection import DEFAULT_STREAM_LIMIT, UnixConnection
from niri_pypc.types.generated.event import Event
from niri_pypc.types.generated.reply import HandledResponse, Reply
from niri_pypc.types.generated.request import EventStreamRequest, Request


@dataclass(slots=True)
class _EventItem:
    event: BaseModel


@dataclass(slots=True)
class _ErrorItem:
    error: Exception


@dataclass(slots=True)
class _ClosedItem:
    pass


_QueueItem = _EventItem | _ErrorItem | _ClosedItem


class NiriEventStream:
    def __init__(self, config: NiriConfig) -> None:
        self._config = config
        self._lifecycle = LifecycleManager()
        self._queue: asyncio.Queue[_QueueItem] | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._connection: UnixConnection | None = None
        self._terminal_cause: Exception | None = None

    @classmethod
    async def connect(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriEventStream:
        if config is None:
            config = NiriConfig()

        instance = cls(config)
        mgr = instance._lifecycle

        await mgr.transition_to(LifecycleState.CONNECTING)

        socket_path = config.resolve_socket_path()
        conn = await UnixConnection.connect(
            socket_path,
            timeout=config.connect_timeout,
            stream_limit=max(config.max_frame_size + 1, DEFAULT_STREAM_LIMIT),
        )
        instance._connection = conn

        await instance._bootstrap(conn)

        instance._queue = asyncio.Queue(maxsize=config.event_queue_capacity)
        instance._reader_task = asyncio.create_task(instance._run_reader())

        await mgr.transition_to(LifecycleState.READY)
        return instance

    async def _bootstrap(self, conn: UnixConnection) -> None:
        """Explicit bootstrap handshake: send EventStream, validate reply."""
        outbound = Request(root=EventStreamRequest()).model_dump_json().encode("utf-8") + b"\n"
        await conn.write_frame(outbound)

        raw = await conn.read_frame(
            max_size=self._config.max_frame_size,
            timeout=self._config.request_timeout,
        )
        reply = Reply.model_validate_json(raw)
        response = reply.unwrap()

        if not isinstance(response, HandledResponse):
            raise ProtocolError(
                f"EventStream bootstrap expected HandledResponse, got {type(response).__name__}",
                operation="event_stream_bootstrap",
            )

    def _enqueue_terminal(self, item: _ErrorItem | _ClosedItem) -> None:
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(item)
            except asyncio.QueueFull:
                pass

    async def _run_reader(self) -> None:
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
                        timeout=None,
                    )
                except TransportError as exc:
                    self._terminal_cause = exc
                    self._enqueue_terminal(_ErrorItem(error=exc))
                    return
                except NiriTimeoutError as exc:
                    self._terminal_cause = exc
                    self._enqueue_terminal(_ErrorItem(error=exc))
                    return

                try:
                    event = Event.model_validate_json(raw)
                except Exception as exc:
                    terminal = DecodeError(
                        f"Failed to decode event: {exc}",
                        operation="event_stream_reader",
                        raw_payload=raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw),
                        cause=exc,
                    )
                    self._terminal_cause = terminal
                    self._enqueue_terminal(_ErrorItem(error=terminal))
                    return

                item = _EventItem(event=event.root)
                if config.backpressure_mode == BackpressureMode.DROP_OLDEST:
                    try:
                        queue.put_nowait(item)
                    except asyncio.QueueFull:
                        logging.getLogger("niri_pypc.event_stream").warning("Event queue full, dropping oldest event")
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        queue.put_nowait(item)
                else:
                    try:
                        queue.put_nowait(item)
                    except asyncio.QueueFull:
                        exc = ProtocolError(
                            "Event queue full (FAIL_FAST mode)",
                            operation="event_stream_reader",
                        )
                        self._terminal_cause = exc
                        self._enqueue_terminal(_ErrorItem(error=exc))
                        return
        finally:
            await self._close_reader_resources()

    async def _close_reader_resources(self) -> None:
        if self._lifecycle.is_terminal:
            return
        try:
            await self._lifecycle.transition_to(LifecycleState.CLOSING)
        except LifecycleError:
            return

        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None

        if self._terminal_cause is None:
            self._enqueue_terminal(_ClosedItem())

        try:
            await self._lifecycle.transition_to(LifecycleState.CLOSED)
        except LifecycleError:
            pass

    async def next(self, *, timeout: float | None = None) -> BaseModel:
        if self._lifecycle.is_terminal:
            if self._terminal_cause is not None:
                raise self._terminal_cause
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

        read_timeout = timeout if timeout is not None else self._config.event_read_timeout
        try:
            item = await asyncio.wait_for(self._queue.get(), timeout=read_timeout)
        except TimeoutError:
            raise NiriTimeoutError(
                "No event received within timeout",
                operation="next",
                retryable=True,
            ) from None

        if isinstance(item, _EventItem):
            return item.event
        if isinstance(item, _ErrorItem):
            raise item.error
        if isinstance(item, _ClosedItem):
            raise LifecycleError(
                "Event stream has been closed",
                operation="next",
                state=self._lifecycle.state.value,
            )

        raise InternalError(
            f"Unexpected queue item type: {type(item).__name__}",
            operation="next",
        )

    def __aiter__(self) -> AsyncIterator[BaseModel]:
        return self._async_iterator()

    async def _async_iterator(self) -> AsyncIterator[BaseModel]:
        while True:
            try:
                yield await self.next()
            except (LifecycleError, StopAsyncIteration):
                break

    async def __anext__(self) -> BaseModel:
        try:
            return await self.next()
        except LifecycleError:
            raise StopAsyncIteration from None

    async def close(self) -> None:
        if self._lifecycle.is_terminal:
            return
        try:
            await self._lifecycle.transition_to(LifecycleState.CLOSING)
        except LifecycleError:
            return

        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass

        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None

        self._enqueue_terminal(_ClosedItem())

        await self._lifecycle.transition_to(LifecycleState.CLOSED)

    async def __aenter__(self) -> NiriEventStream:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
