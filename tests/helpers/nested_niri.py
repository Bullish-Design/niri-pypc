"""Nested niri harness for windowed E2E testing."""

from __future__ import annotations

import asyncio
import os
import shutil
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
    startup_time_s: float = 0.0


class NestedNiriHarness:
    """Harness for launching and managing nested niri instances."""

    def __init__(self, fixtures_root: Path | None = None):
        self.fixtures_root = fixtures_root or Path(__file__).parent.parent / "fixtures"
        self._scenarios: dict[str, NestedNiriScenario] = {}

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
        env["XDG_RUNTIME_DIR"] = str(runtime_dir)

        config_path = self.fixtures_root / "niri" / "configs" / scenario.config_fixture

        cmd = [niri_binary, "--config", str(config_path)]

        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=open(logs_dir / "stdout.log", "wb"),
            stderr=open(logs_dir / "stderr.log", "wb"),
            start_new_session=True,
        )

        start_time = time.time()

        socket_path = await self._wait_for_socket(
            runtime_dir,
            scenario.runtime.startup_timeout_s,
            scenario.runtime.ready_probe_interval_s,
        )

        if socket_path is None:
            process.terminate()
            shutil.rmtree(temp_root)
            raise RuntimeError(f"Nested niri failed to start within {scenario.runtime.startup_timeout_s}s")

        startup_time = time.time() - start_time

        await asyncio.sleep(scenario.runtime.settle_delay_s)

        return NestedNiriInstance(
            socket_path=socket_path,
            runtime_dir=temp_root,
            logs_dir=logs_dir,
            artifacts_dir=artifacts_dir,
            process=process,
            scenario=scenario,
            startup_time_s=startup_time,
        )

    async def _wait_for_socket(
        self,
        runtime_dir: Path,
        timeout: float,
        interval: float,
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
            for f in runtime_dir.iterdir():
                if f.name.startswith("niri-ipc"):
                    if f.is_socket():
                        return f
            await asyncio.sleep(interval)

        return None

    async def stop(self, instance: NestedNiriInstance) -> None:
        """Stop a nested niri instance and cleanup.

        Args:
            instance: Running instance to stop
        """
        instance.process.terminate()

        try:
            instance.process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            instance.process.kill()
            instance.process.wait()

        shutil.rmtree(instance.runtime_dir.parent)

    def get_log_tail(self, instance: NestedNiriInstance, lines: int = 50) -> str:
        """Get last N lines of niri logs for failure diagnosis.

        Args:
            instance: Running instance
            lines: Number of lines to retrieve

        Returns:
            Log tail as string
        """
        stderr_log = instance.logs_dir / "stderr.log"
        if stderr_log.exists():
            with open(stderr_log) as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        return ""
