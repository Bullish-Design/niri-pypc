"""Command client for niri IPC."""

from __future__ import annotations

from typing import Any, overload

from niri_pypc.config import NiriConfig
from niri_pypc.errors import LifecycleError
from niri_pypc.transport.connection import DEFAULT_STREAM_LIMIT, UnixConnection
from niri_pypc.types.generated.reply import (
    FocusedOutputResponse,
    FocusedWindowResponse,
    HandledResponse,
    KeyboardLayoutsResponse,
    LayersResponse,
    OutputConfigChangedResponse,
    OutputsResponse,
    OverviewStateResponse,
    PickedColorResponse,
    PickedWindowResponse,
    Reply,
    ResponseValue,
    VersionResponse,
    WindowsResponse,
    WorkspacesResponse,
)
from niri_pypc.types.generated.request import (
    ActionRequest,
    EventStreamRequest,
    FocusedOutputRequest,
    FocusedWindowRequest,
    KeyboardLayoutsRequest,
    LayersRequest,
    OutputRequest,
    OutputsRequest,
    OverviewStateRequest,
    PickColorRequest,
    PickWindowRequest,
    Request,
    RequestValue,
    ReturnErrorRequest,
    VersionRequest,
    WindowsRequest,
    WorkspacesRequest,
)


class NiriClient:
    def __init__(self, config: NiriConfig) -> None:
        self._config = config
        self._closed = False

    @classmethod
    def create(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriClient:
        if config is None:
            config = NiriConfig()
        config.resolve_socket_path()
        return cls(config)

    @classmethod
    def connect(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriClient:
        """Deprecated alias for `create()`; kept for compatibility."""
        return cls.create(config)

    @overload
    async def request(self, req: ActionRequest, *, timeout: float | None = None) -> HandledResponse: ...
    @overload
    async def request(self, req: EventStreamRequest, *, timeout: float | None = None) -> HandledResponse: ...
    @overload
    async def request(self, req: FocusedOutputRequest, *, timeout: float | None = None) -> FocusedOutputResponse: ...
    @overload
    async def request(self, req: FocusedWindowRequest, *, timeout: float | None = None) -> FocusedWindowResponse: ...
    @overload
    async def request(
        self, req: KeyboardLayoutsRequest, *, timeout: float | None = None
    ) -> KeyboardLayoutsResponse: ...
    @overload
    async def request(self, req: LayersRequest, *, timeout: float | None = None) -> LayersResponse: ...
    @overload
    async def request(self, req: OutputRequest, *, timeout: float | None = None) -> OutputConfigChangedResponse: ...
    @overload
    async def request(self, req: OutputsRequest, *, timeout: float | None = None) -> OutputsResponse: ...
    @overload
    async def request(self, req: OverviewStateRequest, *, timeout: float | None = None) -> OverviewStateResponse: ...
    @overload
    async def request(self, req: PickColorRequest, *, timeout: float | None = None) -> PickedColorResponse: ...
    @overload
    async def request(self, req: PickWindowRequest, *, timeout: float | None = None) -> PickedWindowResponse: ...
    @overload
    async def request(self, req: ReturnErrorRequest, *, timeout: float | None = None) -> HandledResponse: ...
    @overload
    async def request(self, req: VersionRequest, *, timeout: float | None = None) -> VersionResponse: ...
    @overload
    async def request(self, req: WindowsRequest, *, timeout: float | None = None) -> WindowsResponse: ...
    @overload
    async def request(self, req: WorkspacesRequest, *, timeout: float | None = None) -> WorkspacesResponse: ...
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
            outbound = Request(root=req).model_dump_json().encode("utf-8")
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
