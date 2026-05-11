"""Command client for niri IPC."""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from niri_pypc.config import NiriConfig
from niri_pypc.errors import LifecycleError
from niri_pypc.runtime.lifecycle import LifecycleManager, LifecycleState
from niri_pypc.transport.connection import UnixConnection
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
        self._lifecycle = LifecycleManager()

    @classmethod
    def connect(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriClient:
        """Create a client. Validates config but does not open a socket yet.

        Returns an async context manager.
        """
        if config is None:
            config = NiriConfig()
        # Validate config by resolving socket path
        config.resolve_socket_path()
        return cls(config)

    async def request(self, req: BaseModel, *, timeout: float | None = None) -> Any:
        """Send a request and return the decoded response payload.

        Flow:
        1. Resolve socket path from config.
        2. Open a new UnixConnection.
        3. Encode request via model's serializer into JSON frame.
        4. Write frame to socket.
        5. Read response frame.
        6. Decode response as Reply and unwrap Ok/Err.
        7. Close connection.
        8. Return decoded Ok payload.

        Args:
            req: A request variant model instance (e.g., VersionRequest()).
            timeout: Override request timeout. If None, use config.request_timeout.

        Returns:
            The decoded Ok payload (Response variant model).

        Raises:
            TransportError: Socket I/O failure.
            NiriTimeoutError: Request exceeded timeout.
            DecodeError: Response could not be decoded.
            RemoteError: Compositor returned an Err response.
            LifecycleError: Client has been closed.
        """
        if self._lifecycle.is_terminal:
            raise LifecycleError(
                "Client is closed",
                operation="request",
                state=self._lifecycle.state.value,
            )

        socket_path = self._config.resolve_socket_path()
        read_timeout = timeout if timeout is not None else self._config.request_timeout

        conn = await UnixConnection.connect(
            socket_path,
            timeout=self._config.connect_timeout,
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
            result = unwrap_reply(reply)
            return result
        finally:
            await conn.close()

    async def close(self) -> None:
        """Close the client. Idempotent.

        After close(), all subsequent request() calls raise LifecycleError.
        """
        if not self._lifecycle.is_terminal:
            await self._lifecycle.transition_to(LifecycleState.CLOSED)

    async def __aenter__(self) -> NiriClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
