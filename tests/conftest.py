"""Shared test fixtures for niri-pypc."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
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
    config.addinivalue_line("markers", "niri_scenario(name): select nested niri scenario fixture")
    config.addinivalue_line("markers", "visible_demo: curated visible nested demo tests")


def pytest_addoption(parser):
    """Add command-line options for nested niri test mode."""
    parser.addoption(
        "--nested-visible",
        action="store_true",
        default=False,
        help="Run nested tests with a visible compositor window instead of headless mode.",
    )
    parser.addoption(
        "--nested-startup-timeout",
        action="store",
        default=None,
        help="Override nested niri startup timeout in seconds.",
    )


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
    a bootstrap reply and configured event frames. Yields (socket_path, control_dict)
    where control_dict has:
    - events: list of event dicts to send
    - bootstrap_reply: dict for the handshake response (default: {"Ok": {"Handled": {}}})
    - received_request: received request frame bytes
    """
    ctrl = {"events": [], "bootstrap_reply": None, "received_request": None}

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return
        ctrl["received_request"] = data
        bootstrap = ctrl.get("bootstrap_reply")
        if bootstrap is None:
            bootstrap = {"Ok": {"Handled": {}}}
        frame = json.dumps(bootstrap).encode() + b"\n"
        writer.write(frame)
        await writer.drain()
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
            frame = json.dumps({"Ok": {"Handled": {}}}).encode() + b"\n"
            writer.write(frame)
            await writer.drain()
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


@pytest.fixture(scope="session")
def nested_harness() -> NestedNiriHarness:
    """Provide a nested niri harness instance."""
    return NestedNiriHarness()


def _visible_mode_requested(config: pytest.Config) -> bool:
    return bool(config.getoption("--nested-visible") or os.environ.get("NIRI_PYPC_NESTED_VISIBLE") == "1")


@pytest.fixture(scope="session")
def visible_nested_session_lock(request: pytest.FixtureRequest):
    """Guard visible nested runs so only one process/session runs at a time."""
    if not _visible_mode_requested(request.config):
        yield
        return

    lock_path = Path("/tmp/niri-pypc-visible-nested.lock")
    lock_file = lock_path.open("a+b")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        pytest.skip("Visible nested tests already running in another process/session")

    try:
        yield
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


@pytest.fixture
async def nested_niri(nested_harness: NestedNiriHarness, request: pytest.FixtureRequest):
    """Provide a running nested niri instance for testing.

    Requires @pytest.mark.nested and @pytest.mark.niri_scenario("key") markers.

    Usage:
        @pytest.mark.nested
        @pytest.mark.niri_scenario("minimal")
        async def test_something(nested_niri):
            config = NiriConfig(socket_path=str(nested_niri.socket_path))
            ...
    """
    scenario_marker = request.node.get_closest_marker("niri_scenario")
    if scenario_marker is None:
        pytest.skip("No niri_scenario marker - cannot run nested test")

    scenario_key = scenario_marker.args[0]
    visible = _visible_mode_requested(request.config)
    startup_timeout_opt = request.config.getoption("--nested-startup-timeout")
    startup_timeout = float(startup_timeout_opt) if startup_timeout_opt else None
    niri_binary = os.environ.get("NIRI_PYPC_NIRI_BINARY", "niri")

    if visible and os.environ.get("NIRI_PYPC_ALLOW_VISIBLE_NESTED") != "1":
        pytest.skip("Visible nested mode requires NIRI_PYPC_ALLOW_VISIBLE_NESTED=1")

    if visible and os.environ.get("PYTEST_XDIST_WORKER"):
        pytest.skip("Visible nested mode is disabled under xdist workers")
    numprocesses = getattr(request.config.option, "numprocesses", None)
    if visible and numprocesses and int(numprocesses) > 1:
        pytest.skip("Visible nested mode requires serial execution (no -n > 1)")

    request.getfixturevalue("visible_nested_session_lock")

    try:
        instance = await nested_harness.start(
            scenario_key,
            niri_binary=niri_binary,
            visible=visible,
            startup_timeout_s=startup_timeout,
        )
    except FileNotFoundError as exc:
        pytest.skip(str(exc))
    except RuntimeError as exc:
        pytest.skip(f"Nested niri could not be started in this environment. Details: {exc}")

    request.node._nested_niri_instance = instance
    try:
        yield instance
    finally:
        request.node._nested_niri_instance = None
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

    if report.when == "call" and report.failed:
        nested_instance = getattr(item, "_nested_niri_instance", None)
        if nested_instance:
            report.sections.append(
                (
                    "Nested Niri Failure Artifacts",
                    f"""Scenario: {nested_instance.scenario.key}
Config Fixture: {nested_instance.scenario.config_fixture}
Runtime Dir: {nested_instance.runtime_dir}
Socket Path: {nested_instance.socket_path}
Startup Time: {nested_instance.startup_time_s:.2f}s
""",
                )
            )
