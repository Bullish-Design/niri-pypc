"""Unit tests for nested niri hardening logic."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.helpers.nested_niri import (
    NestedNiriHarness,
    NestedNiriScenario,
    ScenarioExpectations,
    ScenarioRuntime,
)


@pytest.mark.asyncio
async def test_wait_for_socket_strict_pid_disables_fallback(tmp_path: Path):
    harness = NestedNiriHarness()
    pid = 12345
    fallback_socket = tmp_path / "niri-ipc.fallback.sock"
    pid_socket = tmp_path / f"niri.{pid}.sock"

    calls = {"count": 0}

    def fake_list(_runtime_dir: Path) -> set[Path]:
        calls["count"] += 1
        if calls["count"] == 1:
            return {fallback_socket}
        return {fallback_socket, pid_socket}

    harness._list_candidate_sockets = fake_list  # type: ignore[method-assign]

    socket_path = await harness._wait_for_socket(
        runtime_dir=tmp_path,
        timeout=1.0,
        interval=0.01,
        pid=pid,
        existing_sockets=set(),
        strict_pid=True,
    )

    assert socket_path == pid_socket


@pytest.mark.asyncio
async def test_wait_for_socket_non_strict_allows_fallback(tmp_path: Path):
    harness = NestedNiriHarness()
    fallback_socket = tmp_path / "niri-ipc.fallback.sock"
    harness._list_candidate_sockets = lambda _runtime_dir: {fallback_socket}  # type: ignore[method-assign]

    socket_path = await harness._wait_for_socket(
        runtime_dir=tmp_path,
        timeout=0.2,
        interval=0.01,
        pid=1,
        existing_sockets=set(),
        strict_pid=False,
    )

    assert socket_path == fallback_socket


def test_visible_preflight_happy_path(tmp_path: Path):
    harness = NestedNiriHarness()
    socket_path = tmp_path / "wayland-1"

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(socket_path))
        env = {
            "WAYLAND_DISPLAY": "wayland-1",
            "XDG_RUNTIME_DIR": str(tmp_path),
            "XDG_SESSION_TYPE": "wayland",
        }
        ok, reason = harness._visible_preflight(env)
        assert ok is True
        assert reason == ""
    finally:
        server.close()
        if socket_path.exists():
            os.unlink(socket_path)


def test_visible_preflight_rejects_missing_socket(tmp_path: Path):
    harness = NestedNiriHarness()
    env = {
        "WAYLAND_DISPLAY": "wayland-9",
        "XDG_RUNTIME_DIR": str(tmp_path),
    }
    ok, reason = harness._visible_preflight(env)
    assert ok is False
    assert "does not exist" in reason


def test_visible_circuit_opens_on_backend_failure_signature():
    harness = NestedNiriHarness()
    harness._maybe_open_visible_circuit("WaylandError(Connection(NoCompositor))\n")
    assert harness._visible_circuit_open is True
    assert harness._visible_circuit_reason == "WaylandError(Connection(NoCompositor))"


class TestStrictManifests:
    def test_scenario_rejects_extra_keys(self):
        with pytest.raises(ValidationError, match="extra"):
            NestedNiriScenario(
                key="test",
                config_fixture="test.kdl",
                nonexistent_field="boom",
            )

    def test_scenario_runtime_rejects_extra_keys(self):
        with pytest.raises(ValidationError, match="extra"):
            ScenarioRuntime(startup_timeout_s=10.0, bogus="nope")

    def test_scenario_expectations_rejects_extra_keys(self):
        with pytest.raises(ValidationError, match="extra"):
            ScenarioExpectations(min_outputs=2, unknown_key=True)

    def test_scenario_runtime_is_frozen(self):
        runtime = ScenarioRuntime()
        with pytest.raises(ValidationError):
            runtime.startup_timeout_s = 99.0

    def test_scenario_is_frozen(self):
        scenario = NestedNiriScenario(key="k", config_fixture="f.kdl")
        with pytest.raises(ValidationError):
            scenario.key = "other"


class TestProtocolReadiness:
    @pytest.mark.asyncio
    async def test_wait_until_protocol_ready_fails_cleanly(self, monkeypatch: pytest.MonkeyPatch):
        harness = NestedNiriHarness()

        import niri_pypc.api.client as client_mod

        async def always_fail(self, req, **kw):
            raise ConnectionError("socket does not exist")

        monkeypatch.setattr(client_mod.NiriClient, "request", always_fail)

        with pytest.raises(RuntimeError, match="IPC protocol did not become ready"):
            await harness._wait_until_protocol_ready(
                socket_path=Path("/nonexistent/missing.sock"),
                timeout_s=0.1,
                interval_s=0.02,
            )
