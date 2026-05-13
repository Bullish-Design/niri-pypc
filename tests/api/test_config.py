"""Tests for the configuration layer."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from niri_pypc.config import BackpressureMode, NiriConfig
from niri_pypc.errors import ConfigError

pytestmark = pytest.mark.contract


class TestNiriConfig:
    def test_defaults(self):
        cfg = NiriConfig()
        assert cfg.socket_path is None
        assert cfg.connect_timeout == 5.0
        assert cfg.request_timeout == 10.0
        assert cfg.event_read_timeout is None
        assert cfg.max_frame_size == 4 * 1024 * 1024
        assert cfg.event_queue_capacity == 256
        assert cfg.backpressure_mode == BackpressureMode.DROP_OLDEST

    def test_explicit_socket_path(self):
        path = Path("/tmp/niri.sock")
        cfg = NiriConfig(socket_path=path)
        assert cfg.resolve_socket_path() == path

    def test_env_socket_path(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NIRI_SOCKET", "/run/user/1000/niri.sock")
        cfg = NiriConfig()
        assert cfg.resolve_socket_path() == Path("/run/user/1000/niri.sock")

    def test_explicit_overrides_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NIRI_SOCKET", "/env/path.sock")
        path = Path("/explicit/path.sock")
        cfg = NiriConfig(socket_path=path)
        assert cfg.resolve_socket_path() == path

    def test_no_socket_path_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NIRI_SOCKET", raising=False)
        cfg = NiriConfig()
        with pytest.raises(ConfigError, match="No socket path"):
            cfg.resolve_socket_path()

    def test_config_is_frozen(self):
        cfg = NiriConfig()
        with pytest.raises(ValidationError):
            cfg.socket_path = Path("/tmp/test.sock")  # type: ignore[misc]

    def test_custom_timeouts(self):
        cfg = NiriConfig(
            connect_timeout=1.0,
            request_timeout=5.0,
            event_read_timeout=30.0,
        )
        assert cfg.connect_timeout == 1.0
        assert cfg.request_timeout == 5.0
        assert cfg.event_read_timeout == 30.0

    def test_backpressure_mode_fail_fast(self):
        cfg = NiriConfig(backpressure_mode=BackpressureMode.FAIL_FAST)
        assert cfg.backpressure_mode == BackpressureMode.FAIL_FAST

    def test_custom_queue_capacity(self):
        cfg = NiriConfig(event_queue_capacity=512)
        assert cfg.event_queue_capacity == 512

    def test_max_frame_size(self):
        cfg = NiriConfig(max_frame_size=8192)
        assert cfg.max_frame_size == 8192

    def test_string_socket_path_is_coerced_to_path(self):
        cfg = NiriConfig(socket_path="/tmp/niri.sock")
        assert cfg.socket_path == Path("/tmp/niri.sock")

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("connect_timeout", 0.0),
            ("connect_timeout", -1.0),
            ("request_timeout", 0.0),
            ("event_read_timeout", -2.0),
            ("max_frame_size", 0),
            ("event_queue_capacity", 0),
        ],
    )
    def test_invalid_positive_fields_raise_validation_error(self, field_name: str, value: float | int):
        with pytest.raises(ValidationError):
            NiriConfig(**{field_name: value})
