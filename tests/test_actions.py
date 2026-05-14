"""Tests for niri_pypc.actions builder functions."""

from __future__ import annotations

import pytest

import niri_pypc.actions as actions_module
from niri_pypc.actions import (
    _coerce_optional_workspace_ref,
    # Internals (import for testing)
    _coerce_workspace_ref,
    # Builders: Column Management
    center_column,
    center_visible_columns,
    # Builders: Window Management
    center_window,
    # Builders: Screencast / Dynamic Cast
    clear_dynamic_cast_target,
    # Builders: Overview
    close_overview,
    close_window,
    consume_or_expel_window_left,
    consume_or_expel_window_right,
    consume_window_into_column,
    do_screen_transition,
    expand_column_to_available_width,
    expel_window_from_column,
    # Builders: Focus — Column
    focus_column,
    focus_column_first,
    focus_column_last,
    focus_column_left,
    focus_column_left_or_last,
    focus_column_or_monitor_left,
    focus_column_or_monitor_right,
    focus_column_right,
    focus_column_right_or_first,
    # Builders: Focus — Layer
    focus_floating,
    # Builders: Focus — Monitor
    focus_monitor,
    focus_monitor_down,
    focus_monitor_left,
    focus_monitor_next,
    focus_monitor_previous,
    focus_monitor_right,
    focus_monitor_up,
    focus_tiling,
    # Builders: Focus — Window
    focus_window,
    focus_window_bottom,
    focus_window_down,
    focus_window_down_or_column_left,
    focus_window_down_or_column_right,
    focus_window_down_or_top,
    focus_window_in_column,
    focus_window_or_monitor_down,
    focus_window_or_monitor_up,
    focus_window_or_workspace_down,
    focus_window_or_workspace_up,
    focus_window_previous,
    focus_window_top,
    focus_window_up,
    focus_window_up_or_bottom,
    focus_window_up_or_column_left,
    focus_window_up_or_column_right,
    # Builders: Focus — Workspace
    focus_workspace,
    focus_workspace_down,
    focus_workspace_previous,
    focus_workspace_up,
    fullscreen_window,
    layout_index,
    layout_next,
    layout_prev,
    # Builders: System
    load_config_file,
    maximize_column,
    maximize_window_to_edges,
    # Builders: Column Movement
    move_column_left,
    move_column_left_or_to_monitor_left,
    move_column_right,
    move_column_right_or_to_monitor_right,
    move_column_to_first,
    move_column_to_index,
    move_column_to_last,
    move_column_to_monitor,
    move_column_to_monitor_down,
    move_column_to_monitor_left,
    move_column_to_monitor_next,
    move_column_to_monitor_previous,
    move_column_to_monitor_right,
    move_column_to_monitor_up,
    move_column_to_workspace,
    move_column_to_workspace_down,
    move_column_to_workspace_up,
    move_floating_window,
    # Builders: Window Movement
    move_window_down,
    move_window_down_or_to_workspace_down,
    move_window_to_floating,
    move_window_to_monitor,
    move_window_to_monitor_down,
    move_window_to_monitor_left,
    move_window_to_monitor_next,
    move_window_to_monitor_previous,
    move_window_to_monitor_right,
    move_window_to_monitor_up,
    move_window_to_tiling,
    move_window_to_workspace,
    move_window_to_workspace_down,
    move_window_to_workspace_up,
    move_window_up,
    move_window_up_or_to_workspace_up,
    move_workspace_down,
    move_workspace_to_index,
    move_workspace_to_monitor,
    move_workspace_to_monitor_down,
    move_workspace_to_monitor_left,
    move_workspace_to_monitor_next,
    move_workspace_to_monitor_previous,
    move_workspace_to_monitor_right,
    move_workspace_to_monitor_up,
    move_workspace_up,
    open_overview,
    pos_adjust_fixed,
    pos_adjust_proportion,
    pos_set_fixed,
    pos_set_proportion,
    # Builders: Monitor Power
    power_off_monitors,
    power_on_monitors,
    quit,
    reset_window_height,
    # Builders: Screenshot
    screenshot,
    screenshot_screen,
    screenshot_window,
    set_column_display,
    set_column_width,
    set_dynamic_cast_monitor,
    set_dynamic_cast_window,
    # Builders: Window Sizing
    set_window_height,
    set_window_urgent,
    set_window_width,
    # Builders: Workspace Management
    set_workspace_name,
    show_hotkey_overlay,
    size_adjust_fixed,
    size_adjust_proportion,
    size_set_fixed,
    size_set_proportion,
    # Builders: Spawn
    spawn,
    spawn_sh,
    swap_window_left,
    swap_window_right,
    switch_focus_between_floating_and_tiling,
    # Builders: Layout
    switch_layout,
    switch_preset_column_width,
    switch_preset_column_width_back,
    switch_preset_window_height,
    switch_preset_window_height_back,
    switch_preset_window_width,
    switch_preset_window_width_back,
    toggle_column_tabbed_display,
    toggle_keyboard_shortcuts_inhibit,
    toggle_overview,
    toggle_window_floating,
    toggle_window_rule_opacity,
    toggle_window_urgent,
    toggle_windowed_fullscreen,
    unset_window_urgent,
    unset_workspace_name,
    # Nested enum helpers
    workspace_by_id,
    workspace_by_index,
    workspace_by_name,
)
from niri_pypc.types.generated.action import Action
from niri_pypc.types.generated.models import (
    AdjustFixedPositionChange,
    AdjustFixedSizeChange,
    AdjustProportionPositionChange,
    AdjustProportionSizeChange,
    ColumnDisplay,
    IdWorkspaceReferenceArg,
    IndexLayoutSwitchTarget,
    IndexWorkspaceReferenceArg,
    LayoutSwitchTarget,
    NameWorkspaceReferenceArg,
    NextLayoutSwitchTarget,
    PositionChange,
    PrevLayoutSwitchTarget,
    SetFixedPositionChange,
    SetFixedSizeChange,
    SetProportionPositionChange,
    SetProportionSizeChange,
    SizeChange,
    WorkspaceReferenceArg,
)
from niri_pypc.types.generated.request import ActionRequest, Request

# ---------------------------------------------------------------------------
# Test category 1: Nested enum helpers
# ---------------------------------------------------------------------------


class TestWorkspaceHelpers:
    def test_workspace_by_id(self):
        ref = workspace_by_id(42)
        assert isinstance(ref, WorkspaceReferenceArg)
        assert isinstance(ref.root, IdWorkspaceReferenceArg)
        assert ref.root.payload == 42

    def test_workspace_by_index(self):
        ref = workspace_by_index(3)
        assert isinstance(ref, WorkspaceReferenceArg)
        assert isinstance(ref.root, IndexWorkspaceReferenceArg)
        assert ref.root.payload == 3

    def test_workspace_by_name(self):
        ref = workspace_by_name("browser")
        assert isinstance(ref, WorkspaceReferenceArg)
        assert isinstance(ref.root, NameWorkspaceReferenceArg)
        assert ref.root.payload == "browser"


class TestSizeChangeHelpers:
    def test_size_set_fixed(self):
        sc = size_set_fixed(800)
        assert isinstance(sc, SizeChange)
        assert isinstance(sc.root, SetFixedSizeChange)
        assert sc.root.payload == 800

    def test_size_set_proportion(self):
        sc = size_set_proportion(0.5)
        assert isinstance(sc, SizeChange)
        assert isinstance(sc.root, SetProportionSizeChange)
        assert sc.root.payload == 0.5

    def test_size_adjust_fixed(self):
        sc = size_adjust_fixed(-10)
        assert isinstance(sc, SizeChange)
        assert isinstance(sc.root, AdjustFixedSizeChange)
        assert sc.root.payload == -10

    def test_size_adjust_proportion(self):
        sc = size_adjust_proportion(0.1)
        assert isinstance(sc, SizeChange)
        assert isinstance(sc.root, AdjustProportionSizeChange)
        assert sc.root.payload == 0.1


class TestPositionChangeHelpers:
    def test_pos_set_fixed(self):
        pc = pos_set_fixed(100.0)
        assert isinstance(pc, PositionChange)
        assert isinstance(pc.root, SetFixedPositionChange)
        assert pc.root.payload == 100.0

    def test_pos_set_proportion(self):
        pc = pos_set_proportion(0.25)
        assert isinstance(pc, PositionChange)
        assert isinstance(pc.root, SetProportionPositionChange)
        assert pc.root.payload == 0.25

    def test_pos_adjust_fixed(self):
        pc = pos_adjust_fixed(-5.0)
        assert isinstance(pc, PositionChange)
        assert isinstance(pc.root, AdjustFixedPositionChange)
        assert pc.root.payload == -5.0

    def test_pos_adjust_proportion(self):
        pc = pos_adjust_proportion(0.05)
        assert isinstance(pc, PositionChange)
        assert isinstance(pc.root, AdjustProportionPositionChange)
        assert pc.root.payload == 0.05


class TestLayoutSwitchTargetHelpers:
    def test_layout_next(self):
        lt = layout_next()
        assert isinstance(lt, LayoutSwitchTarget)
        assert isinstance(lt.root, NextLayoutSwitchTarget)

    def test_layout_prev(self):
        lt = layout_prev()
        assert isinstance(lt, LayoutSwitchTarget)
        assert isinstance(lt.root, PrevLayoutSwitchTarget)

    def test_layout_index(self):
        lt = layout_index(2)
        assert isinstance(lt, LayoutSwitchTarget)
        assert isinstance(lt.root, IndexLayoutSwitchTarget)
        assert lt.root.payload == 2


# ---------------------------------------------------------------------------
# Test category 2: Workspace coercion
# ---------------------------------------------------------------------------


class TestCoerceWorkspaceRef:
    def test_int_becomes_id(self):
        ref = _coerce_workspace_ref(42)
        assert isinstance(ref.root, IdWorkspaceReferenceArg)
        assert ref.root.payload == 42

    def test_str_becomes_name(self):
        ref = _coerce_workspace_ref("browser")
        assert isinstance(ref.root, NameWorkspaceReferenceArg)
        assert ref.root.payload == "browser"

    def test_passthrough(self):
        original = workspace_by_index(3)
        assert _coerce_workspace_ref(original) is original

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            _coerce_workspace_ref(3.14)  # type: ignore

    def test_optional_none(self):
        assert _coerce_optional_workspace_ref(None) is None

    def test_optional_int(self):
        ref = _coerce_optional_workspace_ref(42)
        assert ref is not None
        assert isinstance(ref.root, IdWorkspaceReferenceArg)


# ---------------------------------------------------------------------------
# Test category 3: Return type assertions (parametrized)
# ---------------------------------------------------------------------------

ALL_BUILDERS = [
    # Spawn
    (spawn, (["ls"],)),
    (spawn_sh, ("ls",)),
    # Focus — Column
    (focus_column, (0,)),
    (focus_column_first, ()),
    (focus_column_last, ()),
    (focus_column_left, ()),
    (focus_column_left_or_last, ()),
    (focus_column_right, ()),
    (focus_column_right_or_first, ()),
    (focus_column_or_monitor_left, ()),
    (focus_column_or_monitor_right, ()),
    # Focus — Window
    (focus_window, (1,)),
    (focus_window_bottom, ()),
    (focus_window_down, ()),
    (focus_window_down_or_column_left, ()),
    (focus_window_down_or_column_right, ()),
    (focus_window_down_or_top, ()),
    (focus_window_in_column, (0,)),
    (focus_window_or_monitor_down, ()),
    (focus_window_or_monitor_up, ()),
    (focus_window_or_workspace_down, ()),
    (focus_window_or_workspace_up, ()),
    (focus_window_previous, ()),
    (focus_window_top, ()),
    (focus_window_up, ()),
    (focus_window_up_or_bottom, ()),
    (focus_window_up_or_column_left, ()),
    (focus_window_up_or_column_right, ()),
    # Focus — Monitor
    (focus_monitor, ("eDP-1",)),
    (focus_monitor_down, ()),
    (focus_monitor_left, ()),
    (focus_monitor_next, ()),
    (focus_monitor_previous, ()),
    (focus_monitor_right, ()),
    (focus_monitor_up, ()),
    # Focus — Workspace
    (focus_workspace, (1,)),
    (focus_workspace_down, ()),
    (focus_workspace_previous, ()),
    (focus_workspace_up, ()),
    # Focus — Layer
    (focus_floating, ()),
    (focus_tiling, ()),
    (switch_focus_between_floating_and_tiling, ()),
    # Window Management
    (center_window, ()),
    (close_window, ()),
    (fullscreen_window, ()),
    (maximize_window_to_edges, ()),
    (reset_window_height, ()),
    (toggle_window_floating, ()),
    (toggle_window_rule_opacity, ()),
    (toggle_windowed_fullscreen, ()),
    (set_window_urgent, (1,)),
    (toggle_window_urgent, (1,)),
    (unset_window_urgent, (1,)),
    # Window Sizing
    (set_window_height, (size_set_fixed(600),)),
    (set_window_width, (size_set_fixed(800),)),
    (switch_preset_window_height, ()),
    (switch_preset_window_height_back, ()),
    (switch_preset_window_width, ()),
    (switch_preset_window_width_back, ()),
    # Window Movement
    (move_window_down, ()),
    (move_window_down_or_to_workspace_down, ()),
    (move_window_to_floating, ()),
    (move_window_to_monitor, ("eDP-1",)),
    (move_window_to_monitor_down, ()),
    (move_window_to_monitor_left, ()),
    (move_window_to_monitor_next, ()),
    (move_window_to_monitor_previous, ()),
    (move_window_to_monitor_right, ()),
    (move_window_to_monitor_up, ()),
    (move_window_to_tiling, ()),
    (move_window_to_workspace, (1,)),
    (move_window_to_workspace_down, ()),
    (move_window_to_workspace_up, ()),
    (move_window_up, ()),
    (move_window_up_or_to_workspace_up, ()),
    (move_floating_window, (pos_set_fixed(0.0), pos_set_fixed(0.0))),
    # Column Management
    (center_column, ()),
    (center_visible_columns, ()),
    (consume_or_expel_window_left, ()),
    (consume_or_expel_window_right, ()),
    (consume_window_into_column, ()),
    (expand_column_to_available_width, ()),
    (expel_window_from_column, ()),
    (maximize_column, ()),
    (set_column_display, (ColumnDisplay.TABBED,)),
    (set_column_width, (size_set_fixed(800),)),
    (switch_preset_column_width, ()),
    (switch_preset_column_width_back, ()),
    (toggle_column_tabbed_display, ()),
    (swap_window_left, ()),
    (swap_window_right, ()),
    # Column Movement
    (move_column_left, ()),
    (move_column_left_or_to_monitor_left, ()),
    (move_column_right, ()),
    (move_column_right_or_to_monitor_right, ()),
    (move_column_to_first, ()),
    (move_column_to_index, (0,)),
    (move_column_to_last, ()),
    (move_column_to_monitor, ("eDP-1",)),
    (move_column_to_monitor_down, ()),
    (move_column_to_monitor_left, ()),
    (move_column_to_monitor_next, ()),
    (move_column_to_monitor_previous, ()),
    (move_column_to_monitor_right, ()),
    (move_column_to_monitor_up, ()),
    (move_column_to_workspace, (1,)),
    (move_column_to_workspace_down, ()),
    (move_column_to_workspace_up, ()),
    # Workspace Management
    (set_workspace_name, ("test",)),
    (unset_workspace_name, ()),
    (move_workspace_down, ()),
    (move_workspace_to_index, (0,)),
    (move_workspace_to_monitor, ("eDP-1",)),
    (move_workspace_to_monitor_down, ()),
    (move_workspace_to_monitor_left, ()),
    (move_workspace_to_monitor_next, ()),
    (move_workspace_to_monitor_previous, ()),
    (move_workspace_to_monitor_right, ()),
    (move_workspace_to_monitor_up, ()),
    (move_workspace_up, ()),
    # Layout
    (switch_layout, (layout_next(),)),
    # Overview
    (close_overview, ()),
    (open_overview, ()),
    (toggle_overview, ()),
    # Screenshot
    (screenshot, ()),
    (screenshot_screen, ()),
    (screenshot_window, ()),
    # Monitor Power
    (power_off_monitors, ()),
    (power_on_monitors, ()),
    # Screencast / Dynamic Cast
    (clear_dynamic_cast_target, ()),
    (set_dynamic_cast_monitor, ()),
    (set_dynamic_cast_window, ()),
    (do_screen_transition, ()),
    # System
    (load_config_file, ()),
    (quit, ()),
    (show_hotkey_overlay, ()),
    (toggle_keyboard_shortcuts_inhibit, ()),
]


@pytest.mark.parametrize(
    "fn,args",
    ALL_BUILDERS,
    ids=lambda x: x.__name__ if callable(x) else str(x),
)
def test_returns_action_request(fn, args):
    result = fn(*args)
    assert isinstance(result, ActionRequest)
    assert isinstance(result.payload, Action)


# ---------------------------------------------------------------------------
# Test category 4: Wire-format round-trip
# ---------------------------------------------------------------------------


class TestWireFormat:
    """Verify builder output serializes to expected niri JSON wire format."""

    def test_spawn(self):
        req = spawn(["alacritty", "--title", "test"])
        wire = Request(req).model_dump(mode="json")
        assert wire == {"Action": {"Spawn": {"command": ["alacritty", "--title", "test"]}}}

    def test_focus_workspace_by_name(self):
        req = focus_workspace("browser")
        wire = Request(req).model_dump(mode="json")
        assert wire == {"Action": {"FocusWorkspace": {"reference": {"Name": "browser"}}}}

    def test_focus_workspace_by_id(self):
        req = focus_workspace(42)
        wire = Request(req).model_dump(mode="json")
        assert wire == {"Action": {"FocusWorkspace": {"reference": {"Id": 42}}}}

    def test_quit_default(self):
        req = quit()
        wire = Request(req).model_dump(mode="json")
        assert wire == {"Action": {"Quit": {"skip_confirmation": False}}}

    def test_quit_force(self):
        req = quit(skip_confirmation=True)
        wire = Request(req).model_dump(mode="json")
        assert wire == {"Action": {"Quit": {"skip_confirmation": True}}}

    def test_set_column_width(self):
        req = set_column_width(size_set_fixed(800))
        wire = Request(req).model_dump(mode="json")
        assert wire == {"Action": {"SetColumnWidth": {"change": {"SetFixed": 800}}}}

    def test_switch_layout_next(self):
        req = switch_layout(layout_next())
        wire = Request(req).model_dump(mode="json")
        assert wire == {"Action": {"SwitchLayout": {"layout": "Next"}}}

    def test_move_window_to_workspace(self):
        req = move_window_to_workspace("coding", focus=False, window_id=5)
        wire = Request(req).model_dump(mode="json")
        assert wire == {
            "Action": {
                "MoveWindowToWorkspace": {
                    "focus": False,
                    "reference": {"Name": "coding"},
                    "window_id": 5,
                }
            }
        }

    def test_move_floating_window(self):
        req = move_floating_window(
            x=pos_adjust_fixed(10.0),
            y=pos_set_fixed(200.0),
        )
        wire = Request(req).model_dump(mode="json")
        assert wire == {
            "Action": {
                "MoveFloatingWindow": {
                    "id": None,
                    "x": {"AdjustFixed": 10.0},
                    "y": {"SetFixed": 200.0},
                }
            }
        }

    def test_parameterless_action(self):
        req = focus_column_left()
        wire = Request(req).model_dump(mode="json")
        assert wire == {"Action": {"FocusColumnLeft": {}}}

    def test_screenshot_defaults(self):
        req = screenshot()
        wire = Request(req).model_dump(mode="json")
        assert wire == {"Action": {"Screenshot": {"path": None, "show_pointer": False}}}


# ---------------------------------------------------------------------------
# Test category 5: Default value assertions
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_quit_default_no_skip(self):
        req = quit()
        assert req.payload.root.skip_confirmation is False

    def test_move_window_to_workspace_default_focus(self):
        req = move_window_to_workspace("test")
        assert req.payload.root.focus is True

    def test_move_column_to_workspace_default_focus(self):
        req = move_column_to_workspace("test")
        assert req.payload.root.focus is True

    def test_move_window_to_workspace_down_default_focus(self):
        req = move_window_to_workspace_down()
        assert req.payload.root.focus is True

    def test_move_column_to_workspace_down_default_focus(self):
        req = move_column_to_workspace_down()
        assert req.payload.root.focus is True

    def test_screenshot_default_no_pointer(self):
        req = screenshot()
        assert req.payload.root.show_pointer is False

    def test_screenshot_screen_default_write_to_disk(self):
        req = screenshot_screen()
        assert req.payload.root.write_to_disk is True

    def test_screenshot_window_default_write_to_disk(self):
        req = screenshot_window()
        assert req.payload.root.write_to_disk is True


# ---------------------------------------------------------------------------
# Test category 6: Completeness meta-tests
# ---------------------------------------------------------------------------

SKIP_DEBUG = {"DebugToggleDamage", "DebugToggleOpaqueRegions", "ToggleDebugTint"}
# Debug-only actions are intentionally not included in ergonomic builders.


def test_all_non_debug_actions_have_builders():
    """Every non-debug action variant should be constructible via a builder."""
    variant_wire_names = {
        v.__niri_wire_name__ for v in Action.__niri_variants__ if v.__niri_wire_name__ not in SKIP_DEBUG
    }
    # ALL_BUILDERS should cover exactly 137 functions (one per non-debug variant)
    assert len(ALL_BUILDERS) == len(variant_wire_names) == 137


def test_all_exports_match():
    """__all__ contains exactly the public functions."""
    exported = set(actions_module.__all__)
    # 14 nested enum helpers + 137 builders = 151
    assert len(exported) == 151
