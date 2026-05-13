"""Raw Unix socket connection wrapper."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from niri_pypc.errors import NiriTimeoutError, ProtocolError, TransportError

DEFAULT_STREAM_LIMIT = 64 * 1024


class UnixConnection:
    """Raw Unix socket connection wrapper.

    Manages a single asyncio StreamReader/StreamWriter pair.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        socket_path: Path,
        *,
        stream_limit: int = DEFAULT_STREAM_LIMIT,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._socket_path = socket_path
        self._closed = False
        self._stream_limit = stream_limit

    @classmethod
    async def connect(
        cls,
        socket_path: Path,
        *,
        timeout: float = 5.0,
        stream_limit: int | None = None,
    ) -> UnixConnection:
        """Open a Unix domain socket connection."""
        limit = stream_limit if stream_limit is not None else DEFAULT_STREAM_LIMIT
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(socket_path), limit=limit),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise NiriTimeoutError(
                f"Connection timed out after {timeout}s",
                operation="connect",
                socket_path=str(socket_path),
                retryable=True,
                cause=exc,
            ) from exc
        except OSError as exc:
            raise TransportError(
                f"Failed to connect: {exc}",
                operation="connect",
                socket_path=str(socket_path),
                retryable=True,
                cause=exc,
            ) from exc

        return cls(reader, writer, socket_path, stream_limit=limit)

    async def write_frame(self, data: bytes) -> None:
        """Write bytes to the socket."""
        if self._closed:
            raise TransportError(
                "Cannot write to closed connection",
                operation="write_frame",
                socket_path=str(self._socket_path),
            )
        try:
            self._writer.write(data)
            await self._writer.drain()
        except OSError as exc:
            self._closed = True
            raise TransportError(
                f"Write failed: {exc}",
                operation="write_frame",
                socket_path=str(self._socket_path),
                retryable=True,
                cause=exc,
            ) from exc

    async def read_frame(
        self,
        *,
        max_size: int = 4 * 1024 * 1024,
        timeout: float | None = None,
    ) -> bytes:
        """Read a newline-terminated frame."""
        if self._closed:
            raise TransportError(
                "Cannot read from closed connection",
                operation="read_frame",
                socket_path=str(self._socket_path),
            )
        try:
            raw = await asyncio.wait_for(
                self._reader.readuntil(b"\n"),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise NiriTimeoutError(
                "Read timed out",
                operation="read_frame",
                socket_path=str(self._socket_path),
                retryable=True,
                cause=exc,
            ) from exc
        except asyncio.IncompleteReadError as exc:
            self._closed = True
            if exc.partial:
                raise TransportError(
                    f"Unexpected EOF after {len(exc.partial)} bytes",
                    operation="read_frame",
                    socket_path=str(self._socket_path),
                    cause=exc,
                ) from exc
            raise TransportError(
                "Connection closed by remote",
                operation="read_frame",
                socket_path=str(self._socket_path),
                cause=exc,
            ) from exc
        except asyncio.LimitOverrunError as exc:
            self._closed = True
            raise ProtocolError(
                f"Frame exceeds maximum {max_size} bytes before delimiter",
                operation="read_frame",
                socket_path=str(self._socket_path),
                cause=exc,
            ) from exc
        except OSError as exc:
            self._closed = True
            raise TransportError(
                f"Read failed: {exc}",
                operation="read_frame",
                socket_path=str(self._socket_path),
                retryable=True,
                cause=exc,
            ) from exc

        frame = raw[:-1]

        if len(frame) > max_size:
            raise ProtocolError(
                f"Frame size {len(frame)} exceeds maximum {max_size}",
                operation="read_frame",
                socket_path=str(self._socket_path),
            )

        return frame

    async def __aenter__(self) -> UnixConnection:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the connection. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except OSError:
            pass

    @property
    def is_closed(self) -> bool:
        return self._closed
