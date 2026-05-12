"""Long-lived visible nested niri demo for niri-pypc."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import sys
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from io import BufferedRandom
from pathlib import Path

from pydantic import BaseModel

from niri_pypc import NiriClient, NiriConfig, NiriConnectionBundle
from niri_pypc.types.generated.action import (
    Action,
    FocusWindowDownAction,
    FocusWindowUpAction,
    FocusWorkspaceDownAction,
    FocusWorkspaceUpAction,
    MoveColumnLeftAction,
    MoveColumnRightAction,
    MoveWindowDownAction,
    MoveWindowToWorkspaceDownAction,
    MoveWindowToWorkspaceUpAction,
    MoveWindowUpAction,
    OpenOverviewAction,
    CloseOverviewAction,
    SpawnShAction,
    ToggleOverviewAction,
)
from niri_pypc.types.generated.models import KeyboardLayouts, LayerSurface, Output, Overview, Window, Workspace
from niri_pypc.types.generated.reply import (
    FocusedOutputResponse,
    FocusedWindowResponse,
    HandledResponse,
    KeyboardLayoutsResponse,
    LayersResponse,
    OutputsResponse,
    OverviewStateResponse,
    VersionResponse,
    WindowsResponse,
    WorkspacesResponse,
)
from niri_pypc.types.generated.request import (
    ActionRequest,
    FocusedOutputRequest,
    FocusedWindowRequest,
    KeyboardLayoutsRequest,
    LayersRequest,
    OutputsRequest,
    OverviewStateRequest,
    VersionRequest,
    WindowsRequest,
    WorkspacesRequest,
)

DEMO_FIXTURES_ROOT = Path(__file__).parent / "fixtures"
VISIBLE_DEMO_LOCK = Path("/tmp/niri-pypc-visible-nested-demo.lock")


@dataclass
class DemoState:
    events_seen: Counter[str]
    snapshots: int = 0
    errors_seen: int = 0
    wire_log: bool = False


def _require_explicit_opt_in() -> None:
    if os.environ.get("NIRI_PYPC_ALLOW_VISIBLE_NESTED") != "1":
        raise RuntimeError("Visible demo requires NIRI_PYPC_ALLOW_VISIBLE_NESTED=1")


def _wire_json(data: object) -> str:
    return json.dumps(data, default=str, ensure_ascii=True, sort_keys=True)


def _wire_log(state: DemoState | None, direction: str, label: str, payload: object) -> None:
    if state is None or not state.wire_log:
        return
    print(f"[demo][wire][{direction}] {label}: {_wire_json(payload)}")


def _acquire_visible_demo_lock() -> BufferedRandom:
    lock_file = VISIBLE_DEMO_LOCK.open("a+b")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock_file.close()
        raise RuntimeError(
            f"Visible demo already running in another process/session (lock: {VISIBLE_DEMO_LOCK})"
        ) from exc
    return lock_file


async def _request_payload(client: NiriClient, request: BaseModel) -> object:
    response = await client.request(request)
    return getattr(response, "payload", None)


async def _safe_call[T](
    label: str,
    fn: Callable[[], Awaitable[T]],
    state: DemoState | None = None,
    default: T | None = None,
) -> T | None:
    try:
        return await fn()
    except Exception as exc:
        if state is not None:
            state.errors_seen += 1
        print(f"[demo] {label} failed: {type(exc).__name__}: {exc}")
        return default


async def _send_action(client: NiriClient, action: Action, state: DemoState | None = None) -> object:
    request = ActionRequest(payload=action)
    _wire_log(state, "out", "ActionRequest", request.model_dump(mode="json"))
    response = await client.request(request)
    _wire_log(state, "in", type(response).__name__, response.model_dump(mode="json"))
    if isinstance(response, HandledResponse):
        return None
    return getattr(response, "payload", None)


async def _request_typed[TResponse](
    client: NiriClient,
    request: BaseModel,
    expected: type[TResponse],
    state: DemoState | None = None,
) -> TResponse:
    _wire_log(state, "out", type(request).__name__, request.model_dump(mode="json"))
    response = await client.request(request)
    _wire_log(state, "in", type(response).__name__, response.model_dump(mode="json"))
    if not isinstance(response, expected):
        raise TypeError(f"Expected {expected.__name__}, got {type(response).__name__}")
    return response


async def _spawn_demo_window(client: NiriClient, spawn_command: str, state: DemoState | None = None) -> bool:
    windows_before = (await _request_typed(client, WindowsRequest(), WindowsResponse, state)).payload
    await _send_action(client, Action(root=SpawnShAction(command=spawn_command)), state)
    await asyncio.sleep(0.8)
    windows_after = (await _request_typed(client, WindowsRequest(), WindowsResponse, state)).payload
    return len(windows_after) > len(windows_before)


async def _run_action_showcase(client: NiriClient, state: DemoState, spawn_command: str) -> None:
    await _safe_call(
        "Spawn extra window #1",
        lambda: _spawn_demo_window(client, spawn_command, state),
        state,
        default=False,
    )
    await _safe_call(
        "Spawn extra window #2",
        lambda: _spawn_demo_window(client, spawn_command, state),
        state,
        default=False,
    )
    await asyncio.sleep(0.4)

    actions: list[tuple[str, Action]] = [
        ("FocusWindowDown", Action(root=FocusWindowDownAction())),
        ("FocusWindowUp", Action(root=FocusWindowUpAction())),
        ("MoveWindowDown", Action(root=MoveWindowDownAction())),
        ("MoveWindowUp", Action(root=MoveWindowUpAction())),
        ("MoveWindowToWorkspaceDown", Action(root=MoveWindowToWorkspaceDownAction(focus=True))),
        ("FocusWorkspaceDown", Action(root=FocusWorkspaceDownAction())),
        ("MoveWindowToWorkspaceUp", Action(root=MoveWindowToWorkspaceUpAction(focus=False))),
        ("FocusWorkspaceUp", Action(root=FocusWorkspaceUpAction())),
        ("MoveColumnRight", Action(root=MoveColumnRightAction())),
        ("MoveColumnLeft", Action(root=MoveColumnLeftAction())),
    ]
    for label, action in actions:
        await _safe_call(label, lambda action=action: _send_action(client, action, state), state, default=None)
        await asyncio.sleep(0.2)


async def _print_snapshot(client: NiriClient, state: DemoState) -> None:
    version_resp = await _safe_call(
        "Version",
        lambda: _request_typed(client, VersionRequest(), VersionResponse, state),
        state,
        default=None,
    )
    outputs_resp = await _safe_call(
        "Outputs",
        lambda: _request_typed(client, OutputsRequest(), OutputsResponse, state),
        state,
        default=None,
    )
    workspaces_resp = await _safe_call(
        "Workspaces",
        lambda: _request_typed(client, WorkspacesRequest(), WorkspacesResponse, state),
        state,
        default=None,
    )
    windows_resp = await _safe_call(
        "Windows",
        lambda: _request_typed(client, WindowsRequest(), WindowsResponse, state),
        state,
        default=None,
    )
    focused_output_resp = await _safe_call(
        "FocusedOutput",
        lambda: _request_typed(client, FocusedOutputRequest(), FocusedOutputResponse, state),
        state,
        default=None,
    )
    focused_window_resp = await _safe_call(
        "FocusedWindow",
        lambda: _request_typed(client, FocusedWindowRequest(), FocusedWindowResponse, state),
        state,
        default=None,
    )
    layers_resp = await _safe_call(
        "Layers",
        lambda: _request_typed(client, LayersRequest(), LayersResponse, state),
        state,
        default=None,
    )
    keyboard_resp = await _safe_call(
        "KeyboardLayouts",
        lambda: _request_typed(client, KeyboardLayoutsRequest(), KeyboardLayoutsResponse, state),
        state,
        default=None,
    )
    overview_resp = await _safe_call(
        "OverviewState",
        lambda: _request_typed(client, OverviewStateRequest(), OverviewStateResponse, state),
        state,
        default=None,
    )

    state.snapshots += 1
    version = version_resp.payload if version_resp is not None else "unknown"
    outputs: dict[str, Output] = outputs_resp.payload if outputs_resp is not None else {}
    workspaces: list[Workspace] = workspaces_resp.payload if workspaces_resp is not None else []
    windows: list[Window] = windows_resp.payload if windows_resp is not None else []
    layers: list[LayerSurface] = layers_resp.payload if layers_resp is not None else []
    keyboard_layouts: KeyboardLayouts | None = keyboard_resp.payload if keyboard_resp is not None else None
    overview: Overview | None = overview_resp.payload if overview_resp is not None else None
    focused_output = focused_output_resp.payload if focused_output_resp is not None else None
    focused_window = focused_window_resp.payload if focused_window_resp is not None else None

    focused_output_name = focused_output.name if focused_output is not None else None
    focused_window_id = focused_window.id if focused_window is not None else None
    keyboard_names = keyboard_layouts.names if keyboard_layouts is not None else []
    overview_open = overview.is_open if overview is not None else None
    print(
        "[demo] snapshot "
        f"#{state.snapshots}: version={version}, outputs={len(outputs)}, "
        f"workspaces={len(workspaces)}, windows={len(windows)}, "
        f"layers={len(layers)}, layouts={keyboard_names}, overview_open={overview_open}, "
        f"focused_output={focused_output_name}, focused_window={focused_window_id}, "
        f"errors={state.errors_seen}"
    )


async def _event_reader(bundle: NiriConnectionBundle, state: DemoState) -> None:
    while True:
        event = await _safe_call("EventStream.next", lambda: bundle.events.next(timeout=30.0), state, default=None)
        if event is None:
            await asyncio.sleep(0.2)
            continue
        event_name = type(event).__name__
        _wire_log(state, "in", event_name, event.model_dump(mode="json"))
        state.events_seen[event_name] += 1
        total = sum(state.events_seen.values())
        if total % 10 == 0:
            top_name, top_count = state.events_seen.most_common(1)[0]
            print(f"[demo] events={total}, top={top_name}:{top_count}")


async def _run_demo(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from tests.helpers.nested_niri import NestedNiriHarness, NestedNiriInstance

    _require_explicit_opt_in()
    lock_file = _acquire_visible_demo_lock()

    harness = NestedNiriHarness(fixtures_root=DEMO_FIXTURES_ROOT)
    instance: NestedNiriInstance | None = None
    event_task: asyncio.Task[None] | None = None

    try:
        instance = await harness.start(
            "visual-demo",
            niri_binary=args.niri_binary,
            visible=True,
            startup_timeout_s=args.startup_timeout,
        )
        startup_details = f"socket={instance.socket_path}, pid={instance.pid}, pgid={instance.pgid}"
        print(f"[demo] started visible nested niri: {startup_details}")

        config = NiriConfig(socket_path=instance.socket_path)
        state = DemoState(events_seen=Counter(), wire_log=args.wire_log)

        async with await NiriConnectionBundle.open(config) as bundle:
            event_task = asyncio.create_task(_event_reader(bundle, state))

            spawned = await _safe_call(
                "Spawn demo window",
                lambda: _spawn_demo_window(bundle.client, args.spawn_command, state),
                state,
                default=False,
            )
            if spawned:
                print("[demo] spawned nested demo client window")
            else:
                print("[demo] no demo window spawned; compositor-only view may remain gray")

            if args.toggle_overview_once:
                await _safe_call(
                    "OpenOverview",
                    lambda: _send_action(bundle.client, Action(root=OpenOverviewAction()), state),
                    state,
                    default=None,
                )
                await asyncio.sleep(0.4)
                await _safe_call(
                    "CloseOverview",
                    lambda: _send_action(bundle.client, Action(root=CloseOverviewAction()), state),
                    state,
                    default=None,
                )
                print("[demo] overview action sequence attempted")

            if args.action_showcase:
                await _run_action_showcase(bundle.client, state, args.spawn_command)
                print("[demo] multi-action showcase sequence attempted")

            await _print_snapshot(bundle.client, state)

            deadline = None if args.duration <= 0 else (asyncio.get_running_loop().time() + args.duration)
            while True:
                await asyncio.sleep(args.snapshot_interval)
                await _print_snapshot(bundle.client, state)
                if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                    print("[demo] duration reached; shutting down")
                    break

        return 0
    finally:
        if event_task is not None:
            event_task.cancel()
            try:
                await event_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                print(f"[demo] event reader exited with error: {exc}", file=sys.stderr)

        if instance is not None:
            await harness.stop(instance)
            print("[demo] nested niri stopped")

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a long-lived visible nested niri demo for niri-pypc.")
    parser.add_argument("--niri-binary", default=os.environ.get("NIRI_PYPC_NIRI_BINARY", "niri"))
    parser.add_argument("--startup-timeout", type=float, default=20.0)
    parser.add_argument("--snapshot-interval", type=float, default=3.0)
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Demo duration in seconds. <=0 means run until Ctrl+C.",
    )
    parser.add_argument(
        "--spawn-command",
        default=(
            "for c in foot alacritty kitty wezterm xterm; do "
            'command -v "$c" >/dev/null 2>&1 && exec "$c"; '
            "done; sleep 0.1"
        ),
        help="Shell command executed inside nested niri to spawn a demo client window.",
    )
    parser.add_argument(
        "--toggle-overview-once",
        action="store_true",
        default=True,
        help="Toggle overview on/off once via IPC action to demonstrate control actions.",
    )
    parser.add_argument(
        "--no-toggle-overview-once",
        action="store_false",
        dest="toggle_overview_once",
        help="Disable overview toggling action.",
    )
    parser.add_argument(
        "--action-showcase",
        action="store_true",
        default=True,
        help="Run a sequence of focus/move/workspace actions after startup.",
    )
    parser.add_argument(
        "--no-action-showcase",
        action="store_false",
        dest="action_showcase",
        help="Disable action showcase sequence.",
    )
    parser.add_argument(
        "--wire-log",
        action="store_true",
        default=os.environ.get("NIRI_PYPC_DEMO_WIRE_LOG") == "1",
        help="Print detailed request/reply/event payloads for demo diagnostics.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        return asyncio.run(_run_demo(args))
    except KeyboardInterrupt:
        print("\n[demo] interrupted; shutting down")
        return 130
    except FileNotFoundError as exc:
        print(f"[demo] binary/config error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"[demo] startup blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
