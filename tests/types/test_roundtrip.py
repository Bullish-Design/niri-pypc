"""Roundtrip tests for generated type models."""

from __future__ import annotations

import pytest

from niri_pypc.types.generated.event import Event
from niri_pypc.types.generated.reply import Reply
from niri_pypc.types.generated.request import Request

pytestmark = pytest.mark.contract


WINDOW = {
    "id": 42,
    "title": "term",
    "app_id": "foot",
    "pid": None,
    "workspace_id": None,
    "focus_timestamp": None,
    "is_focused": True,
    "is_floating": False,
    "is_urgent": False,
    "layout": {
        "pos_in_scrolling_layout": None,
        "tile_pos_in_workspace_view": None,
        "tile_size": [100.0, 50.0],
        "window_offset_in_tile": [0.0, 0.0],
        "window_size": [100, 50],
    },
}

WORKSPACE = {
    "id": 1,
    "idx": 0,
    "name": "main",
    "output": "eDP-1",
    "is_urgent": False,
    "is_focused": True,
    "is_active": True,
    "active_window_id": 42,
}

OUTPUT = {
    "name": "eDP-1",
    "make": "ACME",
    "model": "Panel",
    "serial": "123",
    "physical_size": [300, 200],
    "logical": {
        "x": 0,
        "y": 0,
        "width": 1920,
        "height": 1080,
        "scale": 1.0,
        "transform": "Normal",
    },
    "current_mode": 0,
    "is_custom_mode": False,
    "modes": [{"width": 1920, "height": 1080, "refresh_rate": 60000, "is_preferred": True}],
    "vrr_supported": False,
    "vrr_enabled": False,
}


@pytest.mark.parametrize(
    ("raw", "expected_dump"),
    [
        pytest.param({"Action": {"FocusColumnLeft": {}}}, None, id="action-request-newtype"),
        pytest.param("EventStream", "EventStream", id="event-stream"),
        pytest.param("FocusedOutput", "FocusedOutput", id="focused-output"),
        pytest.param("FocusedWindow", "FocusedWindow", id="focused-window"),
        pytest.param("KeyboardLayouts", "KeyboardLayouts", id="keyboard-layouts"),
        pytest.param("Layers", "Layers", id="layers"),
        pytest.param({"Output": {"action": "On", "output": "HDMI-A-1"}}, None, id="output-struct"),
        pytest.param("Outputs", "Outputs", id="outputs"),
        pytest.param("OverviewState", "OverviewState", id="overview-state"),
        pytest.param("PickColor", "PickColor", id="pick-color"),
        pytest.param("PickWindow", "PickWindow", id="pick-window"),
        pytest.param("ReturnError", "ReturnError", id="return-error"),
        pytest.param("Version", "Version", id="version"),
        pytest.param("Windows", "Windows", id="windows"),
        pytest.param("Workspaces", "Workspaces", id="workspaces"),
    ],
)
def test_request_variants_roundtrip(raw, expected_dump):
    decoded = Request.model_validate(raw)
    dumped = decoded.model_dump(mode="json")
    if expected_dump is not None:
        assert dumped == expected_dump
        return
    assert dumped == raw


@pytest.mark.parametrize(
    ("raw", "expected_dump"),
    [
        pytest.param({"ConfigLoaded": {"failed": False}}, None, id="config-loaded"),
        pytest.param({"KeyboardLayoutSwitched": {"idx": 1}}, None, id="keyboard-layout-switched"),
        pytest.param(
            {"KeyboardLayoutsChanged": {"keyboard_layouts": {"current_idx": 1, "names": ["us", "de"]}}},
            None,
            id="keyboard-layouts-changed",
        ),
        pytest.param({"OverviewOpenedOrClosed": {"is_open": True}}, None, id="overview-opened-or-closed"),
        pytest.param({"ScreenshotCaptured": {"path": "/tmp/shot.png"}}, None, id="screenshot-captured"),
        pytest.param({"WindowClosed": {"id": 42}}, None, id="window-closed"),
        pytest.param({"WindowFocusChanged": {"id": 42}}, None, id="window-focus-changed"),
        pytest.param(
            {"WindowFocusTimestampChanged": {"id": 42, "focus_timestamp": {"secs": 1, "nanos": 2}}},
            None,
            id="window-focus-timestamp-changed",
        ),
        pytest.param(
            {
                "WindowLayoutsChanged": {
                    "changes": [
                        [
                            42,
                            {"tile_size": [100.0, 50.0], "window_offset_in_tile": [0.0, 0.0], "window_size": [100, 50]},
                        ]
                    ]
                }
            },
            {
                "WindowLayoutsChanged": {
                    "changes": [
                        [
                            42,
                            {
                                "pos_in_scrolling_layout": None,
                                "tile_pos_in_workspace_view": None,
                                "tile_size": [100.0, 50.0],
                                "window_offset_in_tile": [0.0, 0.0],
                                "window_size": [100, 50],
                            },
                        ]
                    ]
                }
            },
            id="window-layouts-changed",
        ),
        pytest.param({"WindowOpenedOrChanged": {"window": WINDOW}}, None, id="window-opened-or-changed"),
        pytest.param({"WindowUrgencyChanged": {"id": 42, "urgent": True}}, None, id="window-urgency-changed"),
        pytest.param({"WindowsChanged": {"windows": [WINDOW]}}, None, id="windows-changed"),
        pytest.param({"WorkspaceActivated": {"id": 1, "focused": True}}, None, id="workspace-activated"),
        pytest.param(
            {"WorkspaceActiveWindowChanged": {"workspace_id": 1, "active_window_id": 42}},
            None,
            id="workspace-active-window-changed",
        ),
        pytest.param({"WorkspaceUrgencyChanged": {"id": 1, "urgent": True}}, None, id="workspace-urgency-changed"),
        pytest.param({"WorkspacesChanged": {"workspaces": [WORKSPACE]}}, None, id="workspaces-changed"),
    ],
)
def test_event_variants_roundtrip(raw, expected_dump):
    decoded = Event.model_validate(raw)
    dumped = decoded.model_dump(mode="json")
    assert dumped == (raw if expected_dump is None else expected_dump)


@pytest.mark.parametrize(
    ("raw", "expected_dump"),
    [
        pytest.param({"Err": "something went wrong"}, None, id="err"),
        pytest.param({"Ok": {"Handled": {}}}, {"Ok": "Handled"}, id="handled"),
        pytest.param({"Ok": {"Version": "25.11"}}, None, id="version"),
        pytest.param({"Ok": {"FocusedOutput": OUTPUT}}, None, id="focused-output"),
        pytest.param({"Ok": {"FocusedWindow": WINDOW}}, None, id="focused-window"),
        pytest.param(
            {"Ok": {"KeyboardLayouts": {"current_idx": 0, "names": ["us", "de"]}}}, None, id="keyboard-layouts"
        ),
        pytest.param(
            {
                "Ok": {
                    "Layers": [
                        {
                            "namespace": "waybar",
                            "output": "eDP-1",
                            "layer": "Top",
                            "keyboard_interactivity": "None",
                        }
                    ]
                }
            },
            None,
            id="layers",
        ),
        pytest.param({"Ok": {"OutputConfigChanged": "Applied"}}, None, id="output-config-changed"),
        pytest.param({"Ok": {"Outputs": {"eDP-1": OUTPUT}}}, None, id="outputs"),
        pytest.param({"Ok": {"OverviewState": {"is_open": False}}}, None, id="overview-state"),
        pytest.param({"Ok": {"PickedColor": {"rgb": [0.1, 0.2, 0.3]}}}, None, id="picked-color"),
        pytest.param({"Ok": {"PickedWindow": WINDOW}}, None, id="picked-window"),
        pytest.param({"Ok": {"Windows": [WINDOW]}}, None, id="windows"),
        pytest.param({"Ok": {"Workspaces": [WORKSPACE]}}, None, id="workspaces"),
    ],
)
def test_reply_variants_roundtrip(raw, expected_dump):
    decoded = Reply.model_validate(raw)
    dumped = decoded.model_dump(mode="json")
    assert dumped == (raw if expected_dump is None else expected_dump)
