"""Command client for niri IPC."""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from niri_pypc.config import NiriConfig
from niri_pypc.errors import LifecycleError
from niri_pypc.transport.connection import DEFAULT_STREAM_LIMIT, UnixConnection
from niri_pypc.transport.framing import decode_frame, encode_frame
from niri_pypc.types.codec import unwrap_reply
from niri_pypc.types.generated.reply import Reply


class NiriClient:
    """Command client for niri IPC.

    Uses one-connection-per-request model: each request() call opens a new
    Unix socket connection, sends the request, reads the response, and closes.
    """

    def __init__(self, config: NiriConfig) -> None:
        self._config = config
        self._closed = False

    @classmethod
    def connect(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriClient:
        """Create a client. Validates config but does not open a socket yet."""
        if config is None:
            config = NiriConfig()
        config.resolve_socket_path()
        return cls(config)

    async def request(self, req: BaseModel, *, timeout: float | None = None) -> Any:
        """Send a request and return the decoded response payload."""
        if self._closed:
            raise LifecycleError(
                "Client is closed",
                operation="request",
                state="closed",
            )

        socket_path = self._config.resolve_socket_path()
        read_timeout = timeout if timeout is not None else self._config.request_timeout

        conn = await UnixConnection.connect(
            socket_path,
            timeout=self._config.connect_timeout,
            stream_limit=max(self._config.max_frame_size + 1, DEFAULT_STREAM_LIMIT),
        )
        try:
            from niri_pypc.types.generated.request import Request as RequestModel

            request_root = RequestModel(variant=cast(Any, req))
            payload = request_root.model_dump(mode="json")
            frame = encode_frame(payload)
            await conn.write_frame(frame)

            raw = await conn.read_frame(
                max_size=self._config.max_frame_size,
                timeout=read_timeout,
            )
            decoded = decode_frame(raw)
            reply = Reply.model_validate(decoded)
            return unwrap_reply(reply)
        finally:
            await conn.close()

    async def close(self) -> None:
        """Close the client. Idempotent."""
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def __aenter__(self) -> NiriClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
