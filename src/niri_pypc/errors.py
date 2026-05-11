"""Error taxonomy for niri-pypc."""

from __future__ import annotations

from typing import Any


class NiriError(Exception):
    """Base exception for all niri-pypc errors."""

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        socket_path: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.operation = operation
        self.socket_path = socket_path
        self.retryable = retryable
        super().__init__(message)


class TransportError(NiriError):
    """Socket or framing I/O failure."""


class NiriTimeoutError(NiriError, TimeoutError):
    """Connect, request, or event read timeout."""


class DecodeError(NiriError):
    """Validation or shape failure during decode."""

    def __init__(
        self,
        message: str,
        *,
        raw_payload: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.raw_payload = raw_payload
        super().__init__(message, **kwargs)


class ProtocolError(NiriError):
    """Wire-level contract violation."""


class RemoteError(NiriError):
    """Error response from the compositor."""

    def __init__(
        self,
        message: str,
        *,
        remote_message: str,
        **kwargs: Any,
    ) -> None:
        self.remote_message = remote_message
        super().__init__(message, **kwargs)


class LifecycleError(NiriError):
    """Invalid state transition or usage."""

    def __init__(
        self,
        message: str,
        *,
        state: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.state = state
        super().__init__(message, **kwargs)


class ConfigError(NiriError):
    """Invalid or unresolved configuration."""


class InternalError(NiriError):
    """Impossible internal state — indicates a bug in niri-pypc."""
