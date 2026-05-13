"""Configuration and socket discovery for niri-pypc."""

from __future__ import annotations

import enum
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, PositiveFloat, PositiveInt

from niri_pypc.errors import ConfigError


class BackpressureMode(enum.Enum):
    DROP_OLDEST = "drop_oldest"
    FAIL_FAST = "fail_fast"


class NiriConfig(BaseModel):
    """Configuration for niri-pypc connections."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    socket_path: Path | None = None
    connect_timeout: PositiveFloat = 5.0
    request_timeout: PositiveFloat = 10.0
    event_read_timeout: PositiveFloat | None = None
    max_frame_size: PositiveInt = 4 * 1024 * 1024  # 4 MiB
    event_queue_capacity: PositiveInt = 256
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
