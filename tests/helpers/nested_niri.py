"""Nested niri harness for windowed E2E testing."""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ScenarioRuntime(BaseModel):
    """Runtime configuration for nested niri scenario."""

    startup_timeout_s: float = 15.0
    ready_probe_interval_s: float = 0.1
    settle_delay_s: float = 0.25
    event_timeout_s: float = 3.0


class ScenarioCapabilities(BaseModel):
    """Capability requirements for nested niri scenario."""

    requires_multi_output: bool = False


class ScenarioExpectations(BaseModel):
    """Expected state for nested niri scenario."""

    min_outputs: int = 1
    min_workspaces: int = 1
    allow_zero_windows: bool = True
    output_names: list[str] = Field(default_factory=list)
    workspace_output_map: dict[str, str] = Field(default_factory=dict)


class NestedNiriScenario(BaseModel):
    """Complete scenario manifest for nested niri testing."""

    key: str
    config_fixture: str
    runtime: ScenarioRuntime = Field(default_factory=ScenarioRuntime)
    capabilities: ScenarioCapabilities = Field(default_factory=ScenarioCapabilities)
    expectations: ScenarioExpectations = Field(default_factory=ScenarioExpectations)


@dataclass
class NestedNiriInstance:
    """Running nested niri instance with metadata."""

    socket_path: Path
    runtime_dir: Path
    logs_dir: Path
    artifacts_dir: Path
    process: subprocess.Popen
    scenario: NestedNiriScenario
    pid: int
    pgid: int | None = None
    startup_time_s: float = 0.0


class NestedNiriHarness:
    """Harness for launching and managing nested niri instances."""

    def __init__(self, fixtures_root: Path | None = None):
        self.fixtures_root = fixtures_root or Path(__file__).parent.parent / "fixtures"
        self._scenarios: dict[str, NestedNiriScenario] = {}
        self._visible_circuit_open = False
        self._visible_circuit_reason = ""

    def load_scenario(self, scenario_key: str) -> NestedNiriScenario:
        """Load scenario manifest by key.

        Args:
            scenario_key: Key name (e.g., "minimal", "multi-output")

        Returns:
            Loaded scenario manifest

        Raises:
            FileNotFoundError: If scenario or config fixture missing
        """
        env_key = os.environ.get("NIRI_PYPC_TEST_SCENARIO")
        if env_key:
            scenario_key = env_key

        if scenario_key in self._scenarios:
            return self._scenarios[scenario_key]

        scenarios_dir = self.fixtures_root / "niri" / "scenarios"
        scenario_file = scenarios_dir / f"scenario-{scenario_key}.yaml"

        if not scenario_file.exists():
            raise FileNotFoundError(f"Scenario file not found: {scenario_file}")

        with open(scenario_file) as f:
            data = yaml.safe_load(f)

        scenario = NestedNiriScenario(**data)

        config_path = self.fixtures_root / "niri" / "configs" / scenario.config_fixture
        if not config_path.exists():
            raise FileNotFoundError(f"Config fixture not found: {config_path}")

        self._scenarios[scenario_key] = scenario
        return scenario

    async def start(
        self,
        scenario_key: str,
        niri_binary: str = "niri",
        visible: bool = False,
        startup_timeout_s: float | None = None,
    ) -> NestedNiriInstance:
        """Start a nested niri instance with the specified scenario.

        Args:
            scenario_key: Scenario to use (e.g., "minimal", "multi-output")
            niri_binary: Path to niri binary

        Returns:
            Running nested niri instance

        Raises:
            RuntimeError: If niri fails to start within timeout
        """
        scenario = self.load_scenario(scenario_key)
        startup_timeout_s = startup_timeout_s or scenario.runtime.startup_timeout_s

        temp_root = Path(tempfile.mkdtemp(prefix="niri_nested_"))
        runtime_dir = temp_root / "runtime"
        logs_dir = temp_root / "logs"
        artifacts_dir = temp_root / "artifacts"

        runtime_dir.mkdir()
        logs_dir.mkdir()
        artifacts_dir.mkdir()

        env = os.environ.copy()
        env.pop("NIRI_SOCKET", None)
        env.pop("NIRI_CONFIG", None)
        parent_runtime_dir = Path(env.get("XDG_RUNTIME_DIR", ""))
        wayland_display = env.get("WAYLAND_DISPLAY")
        socket_scan_dir = runtime_dir
        existing_sockets = self._list_candidate_sockets(runtime_dir)
        if visible:
            if self._visible_circuit_open:
                shutil.rmtree(temp_root)
                raise RuntimeError(f"Visible circuit open: {self._visible_circuit_reason}")
            # Visible nested mode: keep the real user runtime dir so this niri
            # instance can connect to the host compositor reliably.
            env["XDG_RUNTIME_DIR"] = str(parent_runtime_dir)
            socket_scan_dir = parent_runtime_dir
            existing_sockets = self._list_candidate_sockets(socket_scan_dir)
            preflight_ok, preflight_reason = self._visible_preflight(env)
            if not preflight_ok:
                shutil.rmtree(temp_root)
                raise RuntimeError(f"Visible preflight failed: {preflight_reason}")
        else:
            env["XDG_RUNTIME_DIR"] = str(runtime_dir)

        if not visible and wayland_display and parent_runtime_dir:
            parent_display_socket = parent_runtime_dir / wayland_display
            if parent_display_socket.exists():
                # Wayland allows absolute socket paths. Keep isolated runtime
                # while pointing the nested client at the host compositor.
                env["WAYLAND_DISPLAY"] = str(parent_display_socket)
            bridged_display_socket = runtime_dir / wayland_display
            if parent_display_socket.exists() and not bridged_display_socket.exists():
                # Bridge the parent compositor socket into the isolated runtime dir
                # so nested niri can connect while still using an isolated IPC location.
                bridged_display_socket.symlink_to(parent_display_socket)
            parent_lock = parent_runtime_dir / f"{wayland_display}.lock"
            bridged_lock = runtime_dir / f"{wayland_display}.lock"
            if parent_lock.exists() and not bridged_lock.exists():
                bridged_lock.symlink_to(parent_lock)

        config_path = self.fixtures_root / "niri" / "configs" / scenario.config_fixture

        cmd = [niri_binary, "--config", str(config_path)]

        resolved_binary = shutil.which(niri_binary)
        if resolved_binary is None:
            shutil.rmtree(temp_root)
            raise FileNotFoundError(f"niri binary not found on PATH: {niri_binary}")

        debug_enabled = os.environ.get("NIRI_PYPC_NESTED_DEBUG") == "1"
        if debug_enabled:
            bridged_display_exists = (runtime_dir / (wayland_display or "")).exists() if wayland_display else False
            print(
                "[nested_niri] launch context:\n"
                f"  scenario={scenario.key}\n"
                f"  visible={visible}\n"
                f"  niri_binary={niri_binary}\n"
                f"  parent_XDG_RUNTIME_DIR={parent_runtime_dir}\n"
                f"  child_XDG_RUNTIME_DIR={runtime_dir}\n"
                f"  socket_scan_dir={socket_scan_dir}\n"
                f"  WAYLAND_DISPLAY={wayland_display}\n"
                f"  bridged_display_exists={bridged_display_exists}\n"
                f"  config={config_path}\n"
                f"  cmd={' '.join(cmd)}"
            )

        with open(logs_dir / "stdout.log", "wb") as stdout_log, open(logs_dir / "stderr.log", "wb") as stderr_log:
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=stdout_log,
                stderr=stderr_log,
                start_new_session=True,
            )
        pgid: int | None = None
        try:
            pgid = os.getpgid(process.pid)
        except OSError:
            pgid = None
        start_time = time.time()

        socket_path = await self._wait_for_socket(
            socket_scan_dir,
            startup_timeout_s,
            scenario.runtime.ready_probe_interval_s,
            pid=process.pid,
            existing_sockets=existing_sockets,
            strict_pid=visible,
        )

        if socket_path is None:
            self._terminate_process_tree(process, pgid=pgid, term_timeout_s=2.0)

            stderr_tail = self.get_log_tail_from_dir(logs_dir)
            if visible:
                self._maybe_open_visible_circuit(stderr_tail)
            if os.environ.get("NIRI_PYPC_KEEP_NESTED_ARTIFACTS") == "1":
                raise RuntimeError(
                    f"Nested niri failed to start within {startup_timeout_s}s.\n"
                    f"Artifacts preserved at: {temp_root}\n"
                    f"stderr tail:\n{stderr_tail}"
                )

            shutil.rmtree(temp_root)
            raise RuntimeError(f"Nested niri failed to start within {startup_timeout_s}s.\nstderr tail:\n{stderr_tail}")

        startup_time = time.time() - start_time

        await asyncio.sleep(scenario.runtime.settle_delay_s)

        return NestedNiriInstance(
            socket_path=socket_path,
            runtime_dir=temp_root,
            logs_dir=logs_dir,
            artifacts_dir=artifacts_dir,
            process=process,
            scenario=scenario,
            pid=process.pid,
            pgid=pgid,
            startup_time_s=startup_time,
        )

    async def _wait_for_socket(
        self,
        runtime_dir: Path,
        timeout: float,
        interval: float,
        pid: int,
        existing_sockets: set[Path],
        strict_pid: bool,
    ) -> Path | None:
        """Wait for niri IPC socket to appear.

        Args:
            runtime_dir: XDG_RUNTIME_DIR to scan
            timeout: Maximum wait time in seconds
            interval: Polling interval in seconds

        Returns:
            Path to discovered socket, or None if timeout
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            for f in self._list_candidate_sockets(runtime_dir):
                if f".{pid}.sock" in f.name:
                    if os.environ.get("NIRI_PYPC_NESTED_DEBUG") == "1":
                        print(f"[nested_niri] strict_pid={strict_pid} socket_match={f}")
                    return f
                if not strict_pid and f not in existing_sockets:
                    if os.environ.get("NIRI_PYPC_NESTED_DEBUG") == "1":
                        print(f"[nested_niri] strict_pid={strict_pid} fallback_socket={f}")
                    return f
            await asyncio.sleep(interval)

        return None

    @staticmethod
    def _list_candidate_sockets(runtime_dir: Path) -> set[Path]:
        sockets: set[Path] = set()
        if not runtime_dir.exists():
            return sockets
        for f in runtime_dir.iterdir():
            if not f.is_socket():
                continue
            if f.name.startswith("niri-ipc") or (f.name.startswith("niri.") and f.name.endswith(".sock")):
                sockets.add(f)
        return sockets

    async def stop(self, instance: NestedNiriInstance) -> None:
        """Stop a nested niri instance and cleanup.

        Args:
            instance: Running instance to stop
        """
        self._terminate_process_tree(instance.process, pgid=instance.pgid, term_timeout_s=5.0)

        shutil.rmtree(instance.runtime_dir)

    def _visible_preflight(self, env: dict[str, str]) -> tuple[bool, str]:
        wayland_display = env.get("WAYLAND_DISPLAY", "")
        if not wayland_display:
            return False, "WAYLAND_DISPLAY is not set"
        runtime_dir = env.get("XDG_RUNTIME_DIR", "")
        if not runtime_dir:
            return False, "XDG_RUNTIME_DIR is not set"
        display_socket = Path(runtime_dir) / wayland_display
        if not display_socket.exists():
            return False, f"WAYLAND_DISPLAY socket does not exist: {display_socket}"
        if not display_socket.is_socket():
            return False, f"WAYLAND_DISPLAY path is not a socket: {display_socket}"
        session_type = env.get("XDG_SESSION_TYPE")
        if session_type and session_type.lower() != "wayland":
            return False, f"XDG_SESSION_TYPE is not wayland: {session_type}"
        return True, ""

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen, pgid: int | None, term_timeout_s: float) -> None:
        if process.poll() is not None:
            return
        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        else:
            process.terminate()

        try:
            process.wait(timeout=term_timeout_s)
            return
        except subprocess.TimeoutExpired:
            pass

        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait()

    def _maybe_open_visible_circuit(self, stderr_tail: str) -> None:
        failure_signatures = (
            "WaylandError(Connection(NoCompositor))",
            "EventLoopCreation(",
            "cannot open display",
        )
        for signature in failure_signatures:
            if signature in stderr_tail:
                self._visible_circuit_open = True
                self._visible_circuit_reason = signature
                return

    def get_log_tail(self, instance: NestedNiriInstance, lines: int = 50) -> str:
        """Get last N lines of niri logs for failure diagnosis.

        Args:
            instance: Running instance
            lines: Number of lines to retrieve

        Returns:
            Log tail as string
        """
        stderr_log = instance.logs_dir / "stderr.log"
        return self.get_log_tail_from_file(stderr_log, lines=lines)

    def get_log_tail_from_dir(self, logs_dir: Path, lines: int = 50) -> str:
        """Get last N lines of stderr log from a logs directory."""
        return self.get_log_tail_from_file(logs_dir / "stderr.log", lines=lines)

    @staticmethod
    def get_log_tail_from_file(stderr_log: Path, lines: int = 50) -> str:
        """Get last N lines from a stderr log file path."""
        if stderr_log.exists():
            with open(stderr_log) as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        return ""
