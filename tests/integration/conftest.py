"""Integration test fixtures for niri-pypc."""

from __future__ import annotations

# Re-export shared fixtures from root conftest
from tests.conftest import (
    mock_command_server,
    mock_event_server,
    mock_unified_server,
    temp_socket_path,
)

__all__ = [
    "mock_command_server",
    "mock_event_server",
    "mock_unified_server",
    "temp_socket_path",
]
