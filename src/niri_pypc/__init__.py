"""niri-pypc: Python protocol client for the niri Wayland compositor."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("niri-pypc")
except PackageNotFoundError:  # local source tree, not installed as a distribution
    __version__ = "0.0.0+local"
from niri_pypc import actions  # noqa: F401
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
