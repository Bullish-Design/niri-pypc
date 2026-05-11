"""niri-pypc: Python protocol client for the niri Wayland compositor."""

from niri_pypc._version import __version__
from niri_pypc.api.bundle import NiriConnectionBundle
from niri_pypc.api.client import NiriClient
from niri_pypc.api.event_stream import NiriEventStream
from niri_pypc.config import BackpressureMode, NiriConfig
from niri_pypc.errors import (
    ConfigError,
    DecodeError,
    EncodeError,
    InternalError,
    LifecycleError,
    NiriError,
    NiriTimeoutError,
    ProtocolError,
    RemoteError,
    TransportError,
)

__all__ = [
    "__version__",
    "BackpressureMode",
    "ConfigError",
    "DecodeError",
    "EncodeError",
    "InternalError",
    "LifecycleError",
    "NiriClient",
    "NiriConfig",
    "NiriConnectionBundle",
    "NiriError",
    "NiriEventStream",
    "NiriTimeoutError",
    "ProtocolError",
    "RemoteError",
    "TransportError",
]
