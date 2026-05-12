# E2E Testing Implementation Guide

## Windowed E2E with Fixture-Based Niri Config for niri-pypc

This guide provides a complete, step-by-step implementation plan for enhancing the niri-pypc test suite with a reliable windowed (nested) niri integration layer. All startup configuration is sourced from fixture files inside the test tree, ensuring deterministic and inspectable test behavior.

---

## Table of Contents

1. [Overview and Goals](#1-overview-and-goals)
2. [Understanding the Test Architecture](#2-understanding-the-test-architecture)
3. [Prerequisites and Setup](#3-prerequisites-and-setup)
4. [File Structure](#4-file-structure)
5. [Step 1: Update pyproject.toml](#5-step-1-update-pyprojecttoml)
6. [Step 2: Create Fixture Directories and KDL Config Files](#6-step-2-create-fixture-directories-and-kdl-config-files)
7. [Step 3: Create Scenario YAML Manifests](#7-step-3-create-scenario-yaml-manifests)
8. [Step 4: Centralize Fake Socket Helpers](#8-step-4-centralize-fake-socket-helpers)
9. [Step 5: Build the Nested Niri Harness](#9-step-5-build-the-nested-niri-harness)
10. [Step 6: Update conftest.py with Markers and Fixtures](#10-step-6-update-conftestpy-with-markers-and-fixtures)
11. [Step 7: Implement Basic Nested Tests](#11-step-7-implement-basic-nested-tests)
12. [Step 8: Implement Event Tests](#12-step-8-implement-event-tests)
13. [Step 9: Mark Existing Tests with Appropriate Markers](#9-step-9-mark-existing-tests-with-appropriate-markers)
14. [Step 10: Run Tests and Verify](#10-step-10-run-tests-and-verify)
15. [Troubleshooting Guide](#troubleshooting-guide)
16. [Definition of Done](#definition-of-done)

---

## 1. Overview and Goals

### 1.1 Primary Objective

Enhance `niri-pypc` end-to-end testing with a reliable windowed (nested) niri integration layer where startup configuration is always sourced from fixture files inside the test tree.

### 1.2 Benefits for Developers

- Inspect and verify exact starting compositor state
- Swap between multiple known configurations
- Run realistic integration scenarios without attaching to their live session

### 1.3 Three Test Bands

| Band | Description | Marker | Use Case |
|------|-------------|--------|----------|
| **Contract Tests** | Socket-only IPC contract tests using fake sockets | `@pytest.mark.contract` | Fast, reliable, default CI |
| **Nested Tests** | Real niri launched as nested/windowed compositor | `@pytest.mark.nested` | Integration testing with real compositor |
| **Smoke Tests** | Manual host-session checks | `@pytest.mark.smoke` | Only when explicitly requested |

---

## 2. Understanding the Test Architecture

### 2.1 Core Principle

**Never inline niri config in Python test code for windowed E2E.** Always point nested niri startup to a checked-in fixture file under `tests/fixtures/niri/configs/`.

### 2.2 Scenario Selection

Each nested E2E test picks a scenario key (or explicit fixture name), and the harness resolves:
- Config path
- Expected capabilities/assumptions
- Optional startup tuning (timeouts, retry windows)

### 2.3 Two Mechanisms for Scenario Selection

1. **Per-test marker/parametrization** selecting scenario fixture
2. **Env override** for local debugging: `NIRI_PYPC_TEST_SCENARIO=multi-output`

### 2.4 Validation Guardrails

- Fail fast if requested scenario/config fixture does not exist
- Log chosen fixture path at test startup
- Include fixture identity in failure output

---

## 3. Prerequisites and Setup

### 3.1 Required Dependencies

Ensure you have the following in your environment:

```bash
# Sync dependencies
devenv shell -- uv sync --extra dev

# Verify pytest is available
devenv shell -- pytest --version
```

### 3.2 Required Packages

The following packages should be in your `pyproject.toml` under `dev`:
- `pytest>=7.0`
- `pytest-asyncio>=0.21.0`
- `pytest-cov>=4.1`
- `PyYAML` (for scenario loading)

---

## 4. File Structure

### 4.1 Target Directory Layout

After implementation, your test structure should look like:

```text
tests/
├── fixtures/
│   ├── ipc/
│   │   └── ...existing and new socket payload fixtures...
│   └── niri/
│       ├── configs/
│       │   ├── base-minimal.kdl
│       │   ├── multi-output.kdl
│       │   └── dense-workspace.kdl
│       └── scenarios/
│           ├── scenario-minimal.yaml
│           ├── scenario-multi-output.yaml
│           └── scenario-dense-workspace.yaml
├── helpers/
│   ├── nested_niri.py
│   └── fake_niri_socket.py
├── integration/
│   ├── test_nested_niri_basic.py
│   └── test_nested_niri_events.py
├── conftest.py (update existing)
├── transport/ (existing)
├── api/ (existing)
├── types/ (existing)
└── live/ (existing, mark as smoke)
```

---

## 5. Step 1: Update pyproject.toml

### 5.1 What to Add

Add pytest markers for test classification.

### 5.2 Code Snippet

Update the `[tool.pytest.ini_options]` section in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "-q --cov=niri_pypc --cov-report=term-missing"
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
  "contract: socket-only IPC contract tests",
  "nested: nested/windowed niri integration tests",
  "smoke: manual real-session checks",
  "niri_scenario(name): select nested niri scenario fixture",
]
```

### 5.3 Action

Run the following to verify the update:

```bash
devenv shell -- pytest --markers | grep -E "(contract|nested|smoke|niri_scenario)"
```

**Expected Output:**

```
contract: socket-only IPC contract tests
nested: nested/windowed niri integration tests
smoke: manual real-session checks
niri_scenario(name): select nested niri scenario fixture
```

---

## 6. Step 2: Create Fixture Directories and KDL Config Files

### 6.1 Create Directories

```bash
mkdir -p tests/fixtures/niri/configs
mkdir -p tests/fixtures/niri/scenarios
mkdir -p tests/helpers
```

### 6.2 base-minimal.kdl

Create `tests/fixtures/niri/configs/base-minimal.kdl`:

```kdl
# Base minimal configuration for nested testing
# Expected invariants: 1 output, 1 active workspace, 0 windows at startup
# NO startup spawns, bars, or session-global programs

output "DP-1" {
    res 1920x1080
    position 0x0
    scale 1.0
}

workspace "1" {
    output "DP-1"
}
```

### 6.3 multi-output.kdl

Create `tests/fixtures/niri/configs/multi-output.kdl`:

```kdl
# Multi-output configuration for nested testing
# Expected invariants: 2 outputs, workspaces mapped to specific outputs
# Used for testing output/workspace mapping behavior

output "DP-1" {
    res 1920x1080
    position 0x0
    scale 1.0
}

output "DP-2" {
    res 1920x1080
    position 1920x0
    scale 1.0
}

workspace "1" {
    output "DP-1"
}

workspace "2" {
    output "DP-2"
}
```

### 6.4 dense-workspace.kdl

Create `tests/fixtures/niri/configs/dense-workspace.kdl`:

```kdl
# Dense workspace configuration for nested testing
# Expected invariants: 1 output, 5+ workspaces for large payload testing
# Designed for testing larger snapshot payloads and queue behavior

output "DP-1" {
    res 1920x1080
    position 0x0
    scale 1.0
}

workspace "1" {
    output "DP-1"
}

workspace "2" {
    output "DP-1"
}

workspace "3" {
    output "DP-1"
}

workspace "4" {
    output "DP-1"
}

workspace "5" {
    output "DP-1"
}
```

### 6.5 Action

Verify files exist:

```bash
ls -la tests/fixtures/niri/configs/
```

**Expected Output:**

```
base-minimal.kdl
multi-output.kdl
dense-workspace.kdl
```

---

## 7. Step 3: Create Scenario YAML Manifests

### 7.1 scenario-minimal.yaml

Create `tests/fixtures/niri/scenarios/scenario-minimal.yaml`:

```yaml
key: minimal
config_fixture: base-minimal.kdl
runtime:
  startup_timeout_s: 15
  ready_probe_interval_s: 0.1
  settle_delay_s: 0.25
  event_timeout_s: 3
capabilities:
  requires_multi_output: false
expectations:
  min_outputs: 1
  min_workspaces: 1
  allow_zero_windows: true
  output_names: []
  workspace_output_map: {}
```

### 7.2 scenario-multi-output.yaml

Create `tests/fixtures/niri/scenarios/scenario-multi-output.yaml`:

```yaml
key: multi-output
config_fixture: multi-output.kdl
runtime:
  startup_timeout_s: 20
  ready_probe_interval_s: 0.1
  settle_delay_s: 0.25
  event_timeout_s: 3
capabilities:
  requires_multi_output: true
expectations:
  min_outputs: 2
  min_workspaces: 2
  allow_zero_windows: true
  output_names:
    - "DP-1"
    - "DP-2"
  workspace_output_map:
    "1": "DP-1"
    "2": "DP-2"
```

### 7.3 scenario-dense-workspace.yaml

Create `tests/fixtures/niri/scenarios/scenario-dense-workspace.yaml`:

```yaml
key: dense-workspace
config_fixture: dense-workspace.kdl
runtime:
  startup_timeout_s: 15
  ready_probe_interval_s: 0.1
  settle_delay_s: 0.25
  event_timeout_s: 3
capabilities:
  requires_multi_output: false
expectations:
  min_outputs: 1
  min_workspaces: 5
  allow_zero_windows: true
  output_names: []
  workspace_output_map: {}
```

### 7.4 Action

Verify files exist:

```bash
ls -la tests/fixtures/niri/scenarios/
```

**Expected Output:**

```
scenario-minimal.yaml
scenario-multi-output.yaml
scenario-dense-workspace.yaml
```

---

## 8. Step 4: Centralize Fake Socket Helpers

### 8.1 What to Create

Create `tests/helpers/fake_niri_socket.py` - a centralized module for reusable mock socket servers.

### 8.2 Code Snippet

Create `tests/helpers/fake_niri_socket.py`:

```python
"""Centralized fake socket helpers for niri-pypc tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FakeSocketConfig:
    """Configuration for fake socket server behavior."""
    response: bytes | None = None
    events: list[dict] = field(default_factory=list)
    received_requests: list[bytes] = field(default_factory=list)
    received_request: bytes | None = None


async def create_command_server(
    response: bytes | None = None,
) -> tuple[Path, FakeSocketConfig]:
    """Create a mock Unix socket server for command-mode testing.
    
    Args:
        response: Bytes to send back as response (or None to close without response)
    
    Returns:
        Tuple of (socket_path, control_config)
    """
    config = FakeSocketConfig(response=response)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return
        config.received_requests.append(data)
        if config.response is not None:
            writer.write(config.response)
            await writer.drain()
        writer.close()

    tmpdir = Path("/tmp") / f"fake_cmd_{id(config)}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    socket_path = tmpdir / "cmd.sock"
    server = await asyncio.start_unsafe_server(handler, path=str(socket_path))
    return socket_path, config


async def create_event_server(
    events: list[dict],
) -> tuple[Path, FakeSocketConfig]:
    """Create a mock Unix socket server for event-stream testing.
    
    Args:
        events: List of event dicts to send to the client
    
    Returns:
        Tuple of (socket_path, control_config)
    """
    config = FakeSocketConfig(events=events)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return
        config.received_request = data
        for evt in config.events:
            frame = json.dumps(evt).encode() + b"\n"
            writer.write(frame)
            await writer.drain()
            await asyncio.sleep(0.01)
        writer.close()

    tmpdir = Path("/tmp") / f"fake_evt_{id(config)}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    socket_path = tmpdir / "evt.sock"
    server = await asyncio.start_unsafe_server(handler, path=str(socket_path))
    return socket_path, config


async def create_unified_server(
    response: bytes | None = None,
    events: list[dict] | None = None,
) -> tuple[Path, FakeSocketConfig, FakeSocketConfig]:
    """Create a single mock server handling both command and event flows.
    
    First connection handles EventStream request (event mode).
    Subsequent connections handle command requests.
    
    Args:
        response: Bytes to send back for command requests
        events: List of event dicts to send for event stream
    
    Returns:
        Tuple of (socket_path, cmd_control, evt_control)
    """
    cmd_config = FakeSocketConfig(response=response)
    evt_config = FakeSocketConfig(events=events or [])
    connection_count = 0

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal connection_count
        connection_count += 1

        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return

        if b"EventStream" in data:
            evt_config.received_request = data
            for evt in evt_config.events:
                frame = json.dumps(evt).encode() + b"\n"
                writer.write(frame)
                await writer.drain()
                await asyncio.sleep(0.01)
            writer.close()
        else:
            cmd_config.received_requests.append(data)
            if cmd_config.response is not None:
                writer.write(cmd_config.response)
                await writer.drain()
            writer.close()

    tmpdir = Path("/tmp") / f"fake_unified_{id(connection_count)}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    socket_path = tmpdir / "unified.sock"
    server = await asyncio.start_unsafe_server(handler, path=str(socket_path))
    return socket_path, cmd_config, evt_config


class MockServer:
    """Context manager for mock socket server lifecycle."""
    
    def __init__(self, socket_path: Path, server: asyncio.Server):
        self.socket_path = socket_path
        self._server = server
    
    async def __aenter__(self) -> "MockServer":
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._server.close()
        await self._server.wait_closed()
        # Cleanup temp directory
        self.socket_path.parent.rmdir()
```

### 8.3 Action

Run linter to verify:

```bash
devenv shell -- ruff check tests/helpers/fake_niri_socket.py
```

---

## 9. Step 5: Build the Nested Niri Harness

### 9.1 What to Create

Create `tests/helpers/nested_niri.py` - the core harness for launching nested niri with proper isolation.

### 9.2 Code Snippet

Create `tests/helpers/nested_niri.py`:

```python
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
        # Check env override first
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
        
        # Validate config fixture exists
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
        
        # Create temp root for this run
        temp_root = Path(tempfile.mkdtemp(prefix="niri_nested_"))
        runtime_dir = temp_root / "runtime"
        logs_dir = temp_root / "logs"
        artifacts_dir = temp_root / "artifacts"
        
        runtime_dir.mkdir()
        logs_dir.mkdir()
        artifacts_dir.mkdir()
        
        # Prepare environment - isolate from host
        env = os.environ.copy()
        env.pop("NIRI_SOCKET", None)
        env.pop("NIRI_CONFIG", None)
        env["XDG_RUNTIME_DIR"] = str(runtime_dir)
        
        # Find niri config fixture
        config_path = self.fixtures_root / "niri" / "configs" / scenario.config_fixture
        
        # Build niri command - NO --session flag
        cmd = [niri_binary, "--config", str(config_path)]
        
        # Start niri process
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=open(logs_dir / "stdout.log", "wb"),
            stderr=open(logs_dir / "stderr.log", "wb"),
            start_new_session=True,
        )
        
        start_time = time.time()
        
        # Discover socket and verify readiness
        socket_path = await self._wait_for_socket(
            runtime_dir,
            scenario.runtime.startup_timeout_s,
            scenario.runtime.ready_probe_interval_s,
        )
        
        if socket_path is None:
            # Cleanup on failure
            process.terminate()
            shutil.rmtree(temp_root)
            raise RuntimeError(
                f"Nested niri failed to start within "
                f"{scenario.runtime.startup_timeout_s}s"
            )
        
        startup_time = time.time() - start_time
        
        # Settle delay
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
            # Look for niri socket files
            for f in runtime_dir.iterdir():
                if f.name.startswith("niri-ipc"):
                    # Verify it's a socket
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
        
        # Cleanup temp directory
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


async def nested_niri_context(
    scenario_key: str,
    niri_binary: str = "niri",
    fixtures_root: Path | None = None,
) -> NestedNiriInstance:
    """Async context manager for nested niri testing.
    
    Usage:
        async with nested_niri_context("minimal") as niri:
            # Use niri.socket_path to connect
            ...
    
    Args:
        scenario_key: Scenario to use
        niri_binary: Path to niri binary
        fixtures_root: Override fixtures root path
    
    Yields:
        Running nested niri instance
    """
    harness = NestedNiriHarness(fixtures_root)
    instance = await harness.start(scenario_key, niri_binary)
    try:
        yield instance
    finally:
        await harness.stop(instance)
```

### 9.3 Add to pyproject.toml

Ensure PyYAML is in dev dependencies. Add to `pyproject.toml`:

```toml
dev = [
  "pytest>=7.0",
  "pytest-asyncio>=0.21.0",
  "pytest-cov>=4.1",
  "ruff>=0.5.0",
  "ty>=0.0.1a11",
  "PyYAML>=6.0",
]
```

### 9.4 Action

Run linter and typecheck:

```bash
devenv shell -- ruff check tests/helpers/nested_niri.py
devenv shell -- ty check tests/helpers/nested_niri.py
```

---

## 10. Step 6: Update conftest.py with Markers and Fixtures

### 10.1 What to Update

Update `tests/conftest.py` to add marker registration, scenario fixture, nested harness fixture, and failure artifact capture.

### 10.2 Code Snippet

Replace `tests/conftest.py` with:

```python
"""Shared test fixtures for niri-pypc."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from tests.helpers.nested_niri import NestedNiriHarness, NestedNiriInstance


# =============================================================================
# MARKER REGISTRATION
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "contract: socket-only IPC contract tests")
    config.addinivalue_line("markers", "nested: nested/windowed niri integration tests")
    config.addinivalue_line("markers", "smoke: manual real-session checks")
    config.addinivalue_line(
        "markers", "niri_scenario(name): select nested niri scenario fixture"
    )


# =============================================================================
# EXISTING SOCKET FIXTURES
# =============================================================================

@pytest.fixture
async def temp_socket_path():
    """Provide a temporary socket path (does not create the socket)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.sock"


@pytest.fixture
async def mock_command_server():
    """Create a mock Unix socket server for command-mode testing.

    Accepts one connection, reads a request frame, sends a canned response,
    then closes. Yields (socket_path, control_dict) where control_dict has:
    - response: bytes to send back (or None to close without response)
    - received_requests: list of received frame bytes
    """
    ctrl = {"response": None, "received_requests": []}

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return
        ctrl["received_requests"].append(data)
        if ctrl["response"] is not None:
            writer.write(ctrl["response"])
            await writer.drain()
        writer.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "cmd.sock"
        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        yield socket_path, ctrl
        server.close()
        await server.wait_closed()


@pytest.fixture
async def mock_event_server():
    """Create a mock Unix socket server for event-stream testing.

    Accepts one connection, reads the EventStream request, then sends
    configured event frames and closes. Yields (socket_path, control_dict)
    where control_dict has:
    - events: list of event dicts to send
    - received_request: received request frame bytes
    """
    ctrl = {"events": [], "received_request": None}

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return
        ctrl["received_request"] = data
        for evt in ctrl["events"]:
            frame = json.dumps(evt).encode() + b"\n"
            writer.write(frame)
            await writer.drain()
            await asyncio.sleep(0.01)
        writer.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "evt.sock"
        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        yield socket_path, ctrl
        server.close()
        await server.wait_closed()


@pytest.fixture
async def mock_unified_server():
    """Create a single mock server handling both command and event flows.

    The first connection handles an EventStream request (event mode).
    Subsequent connections handle command requests.

    Yields (socket_path, cmd_ctrl, evt_ctrl).
    """
    cmd_ctrl = {"response": None, "received_requests": []}
    evt_ctrl = {"events": [], "received_request": None}
    connection_count = 0

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal connection_count
        connection_count += 1

        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return

        if b"EventStream" in data:
            evt_ctrl["received_request"] = data
            for evt in evt_ctrl["events"]:
                frame = json.dumps(evt).encode() + b"\n"
                writer.write(frame)
                await writer.drain()
                await asyncio.sleep(0.01)
            writer.close()
        else:
            cmd_ctrl["received_requests"].append(data)
            if cmd_ctrl["response"] is not None:
                writer.write(cmd_ctrl["response"])
                await writer.drain()
            writer.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "unified.sock"
        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        yield socket_path, cmd_ctrl, evt_ctrl
        server.close()
        await server.wait_closed()


# =============================================================================
# NESTED NIRI FIXTURES
# =============================================================================

@pytest.fixture
def nested_harness() -> NestedNiriHarness:
    """Provide a nested niri harness instance."""
    return NestedNiriHarness()


@pytest.fixture
async def nested_niri(nested_harness: NestedNiriHarness, request: pytest.FixtureRequest):
    """Provide a running nested niri instance for testing.
    
    Requires @pytest.mark.nested and @pytest.mark.niri_scenario("key") markers.
    
    Usage:
        @pytest.mark.nested
        @pytest.mark.niri_scenario("minimal")
        async def test_something(nested_niri):
            config = NiriConfig(socket_path=nested_niri.socket_path)
            ...
    """
    # Extract scenario from marker
    scenario_marker = request.node.get_closest_marker("niri_scenario")
    if scenario_marker is None:
        pytest.skip("No niri_scenario marker - cannot run nested test")
    
    scenario_key = scenario_marker.args[0]
    instance = await nested_harness.start(scenario_key)
    yield instance
    await nested_harness.stop(instance)


@pytest.fixture
def scenario_expectations(nested_niri: NestedNiriInstance):
    """Provide scenario expectations for assertions."""
    return nested_niri.scenario.expectations


# =============================================================================
# FAILURE ARTIFACT CAPTURE
# =============================================================================

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Add failure artifact information to test reports."""
    outcome = yield
    report = outcome.get_result()
    
    # Only add extra info for failed nested tests
    if report.when == "call" and report.failed:
        nested_instance = getattr(item, "_nested_niri_instance", None)
        if nested_instance:
            report.sections.append((
                "Nested Niri Failure Artifacts",
                f"""Scenario: {nested_instance.scenario.key}
Config Fixture: {nested_instance.scenario.config_fixture}
Runtime Dir: {nested_instance.runtime_dir}
Socket Path: {nested_instance.socket_path}
Startup Time: {nested_instance.startup_time_s:.2f}s
"""
            ))
```

### 10.3 Action

Run linter:

```bash
devenv shell -- ruff check tests/conftest.py
```

---

## 11. Step 7: Implement Basic Nested Tests

### 11.1 What to Create

Create `tests/integration/test_nested_niri_basic.py` - basic nested niri tests for version, outputs, workspaces, and windows requests.

### 11.2 Code Snippet

Create `tests/integration/test_nested_niri_basic.py`:

```python
"""Basic nested niri integration tests."""

from __future__ import annotations

import pytest

from niri_pypc import NiriClient, NiriConfig
from niri_pypc.types import VersionRequest, OutputsRequest, WorkspacesRequest, WindowsRequest


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_version_request_round_trip(nested_niri):
    """Test that Version request succeeds on nested socket.
    
    Expected: Request round-trip succeeds, returns valid version info.
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient(config) as client:
        version = await client.send(VersionRequest())
        
        assert version is not None
        assert hasattr(version, "version")
        print(f"Version response: {version.version}")


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_outputs_snapshot_matches_manifest(nested_niri, scenario_expectations):
    """Test that Outputs request matches scenario manifest expectations.
    
    Expected: At least min_outputs outputs returned.
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient(config) as client:
        outputs = await client.send(OutputsRequest())
        
        assert outputs is not None
        assert len(outputs) >= scenario_expectations.min_outputs
        print(f"Outputs: {[o.name for o in outputs]}")
        
        if scenario_expectations.output_names:
            output_names = [o.name for o in outputs]
            for expected_name in scenario_expectations.output_names:
                assert expected_name in output_names


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_workspaces_snapshot_matches_manifest(nested_niri, scenario_expectations):
    """Test that Workspaces request matches scenario manifest expectations.
    
    Expected: At least min_workspaces workspaces returned.
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient(config) as client:
        workspaces = await client.send(WorkspacesRequest())
        
        assert workspaces is not None
        assert len(workspaces) >= scenario_expectations.min_workspaces
        print(f"Workspaces: {[(w.name, w.output) for w in workspaces]}")
        
        # Check workspace->output mapping if specified
        if scenario_expectations.workspace_output_map:
            for ws in workspaces:
                if ws.name in scenario_expectations.workspace_output_map:
                    expected_output = scenario_expectations.workspace_output_map[ws.name]
                    assert ws.output == expected_output


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_windows_request_decodes_on_nested_socket(nested_niri, scenario_expectations):
    """Test that Windows request decodes properly on nested socket.
    
    Expected: Request succeeds and decodes (may be empty at startup).
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient(config) as client:
        windows = await client.send(WindowsRequest())
        
        assert windows is not None
        # Allow zero windows at startup if scenario expects it
        if not scenario_expectations.allow_zero_windows:
            assert len(windows) > 0
        print(f"Windows count: {len(windows)}")


@pytest.mark.nested
@pytest.mark.niri_scenario("multi-output")
async def test_nested_multi_output_scenario(nested_niri, scenario_expectations):
    """Test multi-output scenario with capability-aware skipping.
    
    Expected: Skip if backend doesn't support multiple outputs.
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient(config) as client:
        outputs = await client.send(OutputsRequest())
        
        if scenario_expectations.capabilities and scenario_expectations.capabilities.requires_multi_output:
            if len(outputs) < scenario_expectations.min_outputs:
                pytest.skip(
                    f"Multi-output scenario requires {scenario_expectations.min_outputs} "
                    f"outputs but only {len(outputs)} available"
                )
        
        assert outputs is not None
        print(f"Multi-output test: {len(outputs)} outputs")


@pytest.mark.nested
@pytest.mark.niri_scenario("dense-workspace")
async def test_nested_dense_workspace_payload(nested_niri, scenario_expectations):
    """Test dense workspace scenario for large payload handling.
    
    Expected: Large number of workspaces handled properly.
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient(config) as client:
        workspaces = await client.send(WorkspacesRequest())
        
        assert workspaces is not None
        assert len(workspaces) >= scenario_expectations.min_workspaces
        print(f"Dense workspace test: {len(workspaces)} workspaces")
```

### 11.3 Action

Run the nested tests:

```bash
devenv shell -- pytest -m nested -v --tb=short
```

**Expected Output (first run):**

```
tests/integration/test_nested_niri_basic.py::test_nested_version_request_round_trip FAILED
...
```

This is expected - you'll need niri installed and potentially a nested backend (X11 or nested Wayland) to actually run. The tests will fail gracefully with clear error messages.

---

## 12. Step 8: Implement Event Tests

### 12.1 What to Create

Create `tests/integration/test_nested_niri_events.py` - event stream tests for nested niri.

### 12.2 Code Snippet

Create `tests/integration/test_nested_niri_events.py`:

```python
"""Event stream tests for nested niri integration."""

from __future__ import annotations

import asyncio

import pytest

from niri_pypc import NiriClient, NiriConfig, NiriEventStream
from niri_pypc.types import VersionRequest


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_event_stream_bootstrap(nested_niri):
    """Test that event stream provides initial state bootstrap.
    
    Expected: Event stream connects and receives initial state events.
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    
    events_received = []

    async def event_handler(event):
        events_received.append(event)

    async with NiriEventStream(config, event_handler):
        # Wait for initial state events
        await asyncio.sleep(nested_niri.scenario.runtime.settle_delay_s)
        
        assert len(events_received) > 0, "No events received from stream"
        print(f"Received {len(events_received)} initial events")


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_output_update_events(nested_niri):
    """Test that output change events are captured.
    
    Expected: Event stream captures output-related events.
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    
    output_events = []

    async def event_handler(event):
        # Look for output-related event types
        event_type = type(event).__name__
        if "Output" in event_type or "Monitor" in event_type:
            output_events.append(event)

    async with NiriEventStream(config, event_handler):
        # Wait and collect events
        await asyncio.sleep(nested_niri.scenario.runtime.event_timeout_s)
        
        print(f"Output events: {len(output_events)}")


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_workspace_change_events(nested_niri):
    """Test that workspace change events are captured.
    
    Expected: Event stream captures workspace-related events.
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    
    workspace_events = []

    async def event_handler(event):
        event_type = type(event).__name__
        if "Workspace" in event_type:
            workspace_events.append(event)

    async with NiriEventStream(config, event_handler):
        # Wait and collect events
        await asyncio.sleep(nested_niri.scenario.runtime.event_timeout_s)
        
        print(f"Workspace events: {len(workspace_events)}")


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_event_stream_lifecycle(nested_niri):
    """Test that event stream can be opened and closed cleanly.
    
    Expected: Stream opens, receives events, closes without errors.
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    
    events_received = []

    async def event_handler(event):
        events_received.append(event)

    stream = NiriEventStream(config, event_handler)
    
    await stream.open()
    assert stream.is_open
    
    await asyncio.sleep(nested_niri.scenario.runtime.settle_delay_s)
    
    await stream.close()
    assert not stream.is_open
    
    print(f"Lifecycle test: received {len(events_received)} events")


@pytest.mark.nested
@pytest.mark.niri_scenario("multi-output")
async def test_nested_multi_output_event_mapping(nested_niri):
    """Test output/workspace mapping in event stream for multi-output.
    
    Expected: Events reflect correct output assignments.
    """
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    
    async with NiriClient(config) as client:
        outputs = await client.send(OutputsRequest())
        
        # Get expectations
        expectations = nested_niri.scenario.expectations
        
        if expectations.capabilities and expectations.capabilities.requires_multi_output:
            if len(outputs) < expectations.min_outputs:
                pytest.skip("Not enough outputs for multi-output test")
        
        print(f"Multi-output event test: {len(outputs)} outputs")
```

### 12.3 Action

Run event tests:

```bash
devenv shell -- pytest -m nested -v --tb=short -k event
```

---

## 9. Step 9: Mark Existing Tests with Appropriate Markers

### 9.1 Overview

Reclassify existing tests to use the new markers.

### 9.2 Tests to Mark as `contract`

These tests should be marked with `@pytest.mark.contract`:

- `tests/transport/test_connection.py`
- `tests/transport/test_framing.py`
- `tests/api/test_client.py`
- `tests/api/test_event_stream.py`
- `tests/api/test_config.py`
- `tests/api/test_bundle.py`
- `tests/api/test_lifecycle.py`
- `tests/integration/test_command_flow.py`
- `tests/integration/test_event_flow.py`
- `tests/integration/test_independence.py`
- `tests/types/test_*.py`

### 9.3 Tests to Mark as `smoke`

The live tests should be marked with `@pytest.mark.smoke`:

- `tests/live/test_live.py`

### 9.4 Code Snippet for Test File Update

For each file, add the marker at the top of the file or on specific tests:

```python
"""Contract tests for transport layer."""

import pytest

pytestmark = pytest.mark.contract
```

Or apply to individual tests:

```python
@pytest.mark.contract
async def test_something():
    ...
```

### 9.5 Action

Check current test markers:

```bash
devenv shell -- pytest --collect-only -q | head -20
```

Apply markers to existing tests. After marking, run:

```bash
devenv shell -- pytest -m contract -v --tb=short
```

**Expected Output:**

```
tests/transport/test_connection.py::test_connection_something PASSED
tests/api/test_client.py::test_client_something PASSED
...
```

---

## 10. Step 10: Run Tests and Verify

### 10.1 Run Contract Tests

```bash
devenv shell -- pytest -m contract -q
```

**Expected Output:**

```
tests/transport/... PASSED
tests/api/... PASSED
tests/integration/... PASSED
tests/types/... PASSED

========== X passed in Y.Zs ==========
```

### 10.2 Run Nested Tests (if niri is installed)

```bash
devenv shell -- pytest -m nested -q
```

**Expected Output:**

```
tests/integration/test_nested_niri_basic.py::test_nested_version_request_round_trip ...
tests/integration/test_nested_niri_events.py::test_nested_event_stream_bootstrap ...
```

Note: These may fail if niri is not installed or nested backend is not available.

### 10.3 Run Smoke Tests (manual only)

```bash
devenv shell -- pytest -m smoke -q
```

**Note:** Smoke tests require a real niri session and should only be run manually.

### 10.4 Quick Test Commands Reference

```bash
# Run only contract tests (default CI)
devenv shell -- pytest -m contract -q

# Run nested tests (opt-in)
devenv shell -- pytest -m nested -q

# Run nested tests excluding slow ones
devenv shell -- pytest -m "nested and not slow" -q

# Run smoke tests (manual only)
devenv shell -- pytest -m smoke -q

# List all tests with markers
devenv shell -- pytest --collect-only -m ""
```

---

## Troubleshooting Guide

### Issue: Nested niri fails to start

**Symptoms:** `RuntimeError: Nested niri failed to start within Xs`

**Solutions:**
1. Verify niri is installed: `which niri`
2. Check if nested backend is available (X11 or nested Wayland)
3. Review logs in the test artifacts directory
4. Increase timeout in scenario YAML if system is slow

### Issue: Socket not discovered

**Symptoms:** `socket_path is None` after timeout

**Solutions:**
1. Check `XDG_RUNTIME_DIR` permissions
2. Verify niri binary path is correct
3. Check stderr logs for niri startup errors
4. Ensure no conflicting niri session is running

### Issue: Tests leak to host socket

**Symptoms:** Tests interact with wrong niri session

**Solutions:**
1. Verify `NIRI_SOCKET` is not inherited (harness should strip it)
2. Always use explicit `socket_path` in test code
3. Check that runtime directory is isolated

### Issue: PyYAML import error

**Symptoms:** `ModuleNotFoundError: No module named 'yaml'`

**Solution:**

```bash
devenv shell -- uv sync --extra dev
```

Or add to pyproject.toml:

```toml
dev = [
  ...
  "PyYAML>=6.0",
]
```

### Issue: Ruff/Typecheck failures

**Solutions:**

```bash
# Fix lint issues
devenv shell -- ruff check .
devenv shell -- ruff format .

# Fix type errors
devenv shell -- ty check .
```

---

## Definition of Done

You have successfully implemented the E2E testing enhancement when all of these are true:

1. **Fixture-first config**: All nested startup config comes only from `tests/fixtures/niri/configs/*.kdl`

2. **Scenario selection works**: Via marker (`@pytest.mark.niri_scenario("minimal")`) and env override (`NIRI_PYPC_TEST_SCENARIO=minimal`)

3. **Host socket isolation**: Nested harness never uses the host `NIRI_SOCKET` - always uses explicit `socket_path`

4. **`minimal` scenario stable**: Tests pass reliably locally and in CI

5. **`multi-output` capability-aware**: Either stable or explicitly skipped with clear reason when backend doesn't support it

6. **`dense-workspace` covers**: Both large payload decoding and deterministic burst/backpressure behavior

7. **Contract tests remain fast**: Socket-contract coverage stays fast and separate from nested tests

8. **Markers applied**: All existing tests properly marked with `contract`, `nested`, or `smoke`

9. **CI integrated**: Tests can be run via:
   - `devenv shell -- pytest -m contract -q` (PR default)
   - `devenv shell -- pytest -m nested -q` (opt-in/nightly)
   - `devenv shell -- pytest -m smoke -q` (manual)

---

## Quick Reference: File Checklist

After implementation, verify these files exist:

```
tests/
├── fixtures/
│   ├── ipc/
│   └── niri/
│       ├── configs/
│       │   ├── base-minimal.kdl
│       │   ├── multi-output.kdl
│       │   └── dense-workspace.kdl
│       └── scenarios/
│           ├── scenario-minimal.yaml
│           ├── scenario-multi-output.yaml
│           └── scenario-dense-workspace.yaml
├── helpers/
│   ├── nested_niri.py
│   └── fake_niri_socket.py
├── integration/
│   ├── test_nested_niri_basic.py
│   └── test_nested_niri_events.py
├── conftest.py (updated)
└── [existing test files marked appropriately]
```

---

## Additional Resources

- [niri IPC Documentation](https://github.com/niri-wm/niri/wiki/IPC)
- [niri Configuration Overview](https://github.com/YaLTeR/niri/wiki/Configuration%3A-Overview)
- [pytest markers documentation](https://docs.pytest.org/en/stable/mark.html)
- [asyncio testing in pytest](https://pytest-asyncio.readthedocs.io/)