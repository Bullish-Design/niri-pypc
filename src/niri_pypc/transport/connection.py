"""Raw Unix socket connection wrapper."""

from __future__ import annotations

import asyncio
from pathlib import Path

from niri_pypc.errors import NiriTimeoutError, ProtocolError, TransportError


class UnixConnection:
    """Raw Unix socket connection wrapper.

    Manages a single asyncio StreamReader/StreamWriter pair.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        socket_path: Path,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._socket_path = socket_path
        self._closed = False

    @classmethod
    async def connect(
        cls,
        socket_path: Path,
        *,
        timeout: float = 5.0,
    ) -> UnixConnection:
        """Open a Unix domain socket connection.

        Raises:
            TransportError: If the socket cannot be reached.
            NiriTimeoutError: If connection exceeds timeout.
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(socket_path)),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise NiriTimeoutError(
                f"Connection timed out after {timeout}s",
                operation="connect",
                socket_path=str(socket_path),
                retryable=True,
            ) from exc
        except OSError as exc:
            raise TransportError(
                f"Failed to connect: {exc}",
                operation="connect",
                socket_path=str(socket_path),
                retryable=True,
            ) from exc

        return cls(reader, writer, socket_path)

    async def write_frame(self, data: bytes) -> None:
        """Write bytes to the socket.

        Raises:
            TransportError: On write failure.
        """
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
            ) from exc

    async def read_frame(
        self,
        *,
        max_size: int = 4 * 1024 * 1024,
        timeout: float | None = None,
    ) -> bytes:
        """Read a newline-terminated frame.

        Args:
            max_size: Maximum frame size in bytes. Frames exceeding this
                       raise ProtocolError.
            timeout: Read timeout in seconds. None = no timeout.

        Returns:
            Raw frame bytes (without trailing newline).

        Raises:
            TransportError: On read failure or unexpected EOF.
            NiriTimeoutError: On timeout.
            ProtocolError: If frame exceeds max_size.
        """
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
            ) from exc
        except asyncio.IncompleteReadError as exc:
            self._closed = True
            if exc.partial:
                raise TransportError(
                    f"Unexpected EOF after {len(exc.partial)} bytes",
                    operation="read_frame",
                    socket_path=str(self._socket_path),
                ) from exc
            raise TransportError(
                "Connection closed by remote",
                operation="read_frame",
                socket_path=str(self._socket_path),
            ) from exc
        except OSError as exc:
            self._closed = True
            raise TransportError(
                f"Read failed: {exc}",
                operation="read_frame",
                socket_path=str(self._socket_path),
                retryable=True,
            ) from exc

        # Strip trailing newline
        frame = raw[:-1]

        if len(frame) > max_size:
            raise ProtocolError(
                f"Frame size {len(frame)} exceeds maximum {max_size}",
                operation="read_frame",
                socket_path=str(self._socket_path),
            )

        return frame

    async def close(self) -> None:
        """Close the connection. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            if hasattr(self._writer, "close"):
                self._writer.close()
                if hasattr(self._writer, "wait_closed"):
                    await self._writer.wait_closed()
        except OSError:
            pass

    @property
    def is_closed(self) -> bool:
        return self._closed
