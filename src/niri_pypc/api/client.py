"""Command client for niri IPC."""

from __future__ import annotations

from typing import Any

from niri_pypc.config import NiriConfig
from niri_pypc.errors import LifecycleError
from niri_pypc.transport.connection import DEFAULT_STREAM_LIMIT, UnixConnection
from niri_pypc.types.generated.reply import Reply, ResponseValue
from niri_pypc.types.generated.request import Request, RequestValue


class NiriClient:
    def __init__(self, config: NiriConfig) -> None:
        self._config = config
        self._closed = False

    @classmethod
    def connect(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriClient:
        if config is None:
            config = NiriConfig()
        config.resolve_socket_path()
        return cls(config)

    async def request(self, req: RequestValue, *, timeout: float | None = None) -> ResponseValue:
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
            outbound = Request(root=req).model_dump_json().encode("utf-8") + b"\n"
            await conn.write_frame(outbound)

            raw = await conn.read_frame(
                max_size=self._config.max_frame_size,
                timeout=read_timeout,
            )
            reply = Reply.model_validate_json(raw)
            return reply.unwrap()
        finally:
            await conn.close()

    async def close(self) -> None:
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def __aenter__(self) -> NiriClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
