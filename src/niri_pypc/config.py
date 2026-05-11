"""Configuration and socket discovery for niri-pypc."""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass
from pathlib import Path

from niri_pypc.errors import ConfigError


class BackpressureMode(enum.Enum):
    DROP_OLDEST = "drop_oldest"
    FAIL_FAST = "fail_fast"


@dataclass(frozen=True, slots=True)
class NiriConfig:
    """Configuration for niri-pypc connections."""

    socket_path: Path | None = None
    connect_timeout: float = 5.0
    request_timeout: float = 10.0
    event_read_timeout: float | None = None
    max_frame_size: int = 4 * 1024 * 1024  # 4 MiB
    event_queue_capacity: int = 256
    backpressure_mode: BackpressureMode = BackpressureMode.DROP_OLDEST

    def resolve_socket_path(self) -> Path:
        """Resolve socket path: explicit path -> NIRI_SOCKET -> ConfigError."""
        if self.socket_path is not None:
            return self.socket_path
        env = os.environ.get("NIRI_SOCKET")
        if env:
            return Path(env)

        raise ConfigError(
            "No socket path: set socket_path or NIRI_SOCKET environment variable",
            operation="resolve_socket_path",
        )
