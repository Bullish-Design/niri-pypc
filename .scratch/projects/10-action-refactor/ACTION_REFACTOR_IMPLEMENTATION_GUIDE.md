# ACTION_REFACTOR_IMPLEMENTATION_GUIDE

Step-by-step guide for implementing `src/niri_pypc/actions.py` and `tests/test_actions.py`.

## Table of Contents

1. [File Overview](#1-file-overview)
2. [Implementation Order](#2-implementation-order)
3. [actions.py — Imports and Internals](#3-actionspy--imports-and-internals)
4. [actions.py — Nested Enum Helpers (14 functions)](#4-actionspy--nested-enum-helpers-14-functions)
5. [actions.py — Builder Functions (137 functions)](#5-actionspy--builder-functions-137-functions)
6. [actions.py — `__all__` Definition](#6-actionspy--__all__-definition)
7. [Package Root Update](#7-package-root-update)
8. [tests/test_actions.py](#8-teststest_actionspy)
9. [Validation Checklist](#9-validation-checklist)

---

## 1. File Overview

| File | Purpose |
|------|---------|
| `src/niri_pypc/actions.py` | All builder functions + nested enum helpers |
| `tests/test_actions.py` | All tests |
| `src/niri_pypc/__init__.py` | Add `actions` re-export (one line) |

## 2. Implementation Order

1. Write `_wrap()` and `_coerce_workspace_ref()` internals.
2. Write the 14 nested enum helpers. Test them.
3. Write Tier 1 builders (14 actions with nested enum params). Test wire format.
4. Write Tier 2 builders (123 actions). Test return types.
5. Write `__all__`.
6. Write completeness meta-test.
7. Update `__init__.py`.

## 3. actions.py — Imports and Internals

```python
"""Ergonomic builder functions for niri IPC actions.

Each function returns an ``ActionRequest`` ready for ``NiriClient.request()``.
"""

from __future__ import annotations

from niri_pypc.types.generated.action import (
    Action,
    ActionValue,
    # -- Tier 1 (nested enum params) --
    FocusWorkspaceAction,
    MoveColumnToWorkspaceAction,
    MoveFloatingWindowAction,
    MoveWindowToWorkspaceAction,
    MoveWorkspaceToIndexAction,
    MoveWorkspaceToMonitorAction,
    SetColumnDisplayAction,
    SetColumnWidthAction,
    SetWindowHeightAction,
    SetWindowWidthAction,
    SetWorkspaceNameAction,
    SwitchLayoutAction,
    UnsetWorkspaceNameAction,
    # -- Tier 2 (all remaining non-debug) --
    CenterColumnAction,
    CenterVisibleColumnsAction,
    CenterWindowAction,
    ClearDynamicCastTargetAction,
    CloseOverviewAction,
    CloseWindowAction,
    ConsumeOrExpelWindowLeftAction,
    ConsumeOrExpelWindowRightAction,
    ConsumeWindowIntoColumnAction,
    DoScreenTransitionAction,
    ExpandColumnToAvailableWidthAction,
    ExpelWindowFromColumnAction,
    FocusColumnAction,
    FocusColumnFirstAction,
    FocusColumnLastAction,
    FocusColumnLeftAction,
    FocusColumnLeftOrLastAction,
    FocusColumnOrMonitorLeftAction,
    FocusColumnOrMonitorRightAction,
    FocusColumnRightAction,
    FocusColumnRightOrFirstAction,
    FocusFloatingAction,
    FocusMonitorAction,
    FocusMonitorDownAction,
    FocusMonitorLeftAction,
    FocusMonitorNextAction,
    FocusMonitorPreviousAction,
    FocusMonitorRightAction,
    FocusMonitorUpAction,
    FocusTilingAction,
    FocusWindowAction,
    FocusWindowBottomAction,
    FocusWindowDownAction,
    FocusWindowDownOrColumnLeftAction,
    FocusWindowDownOrColumnRightAction,
    FocusWindowDownOrTopAction,
    FocusWindowInColumnAction,
    FocusWindowOrMonitorDownAction,
    FocusWindowOrMonitorUpAction,
    FocusWindowOrWorkspaceDownAction,
    FocusWindowOrWorkspaceUpAction,
    FocusWindowPreviousAction,
    FocusWindowTopAction,
    FocusWindowUpAction,
    FocusWindowUpOrBottomAction,
    FocusWindowUpOrColumnLeftAction,
    FocusWindowUpOrColumnRightAction,
    FocusWorkspaceDownAction,
    FocusWorkspacePreviousAction,
    FocusWorkspaceUpAction,
    FullscreenWindowAction,
    LoadConfigFileAction,
    MaximizeColumnAction,
    MaximizeWindowToEdgesAction,
    MoveColumnLeftAction,
    MoveColumnLeftOrToMonitorLeftAction,
    MoveColumnRightAction,
    MoveColumnRightOrToMonitorRightAction,
    MoveColumnToFirstAction,
    MoveColumnToIndexAction,
    MoveColumnToLastAction,
    MoveColumnToMonitorAction,
    MoveColumnToMonitorDownAction,
    MoveColumnToMonitorLeftAction,
    MoveColumnToMonitorNextAction,
    MoveColumnToMonitorPreviousAction,
    MoveColumnToMonitorRightAction,
    MoveColumnToMonitorUpAction,
    MoveColumnToWorkspaceDownAction,
    MoveColumnToWorkspaceUpAction,
    MoveWindowDownAction,
    MoveWindowDownOrToWorkspaceDownAction,
    MoveWindowToFloatingAction,
    MoveWindowToMonitorAction,
    MoveWindowToMonitorDownAction,
    MoveWindowToMonitorLeftAction,
    MoveWindowToMonitorNextAction,
    MoveWindowToMonitorPreviousAction,
    MoveWindowToMonitorRightAction,
    MoveWindowToMonitorUpAction,
    MoveWindowToTilingAction,
    MoveWindowToWorkspaceDownAction,
    MoveWindowToWorkspaceUpAction,
    MoveWindowUpAction,
    MoveWindowUpOrToWorkspaceUpAction,
    MoveWorkspaceDownAction,
    MoveWorkspaceToMonitorDownAction,
    MoveWorkspaceToMonitorLeftAction,
    MoveWorkspaceToMonitorNextAction,
    MoveWorkspaceToMonitorPreviousAction,
    MoveWorkspaceToMonitorRightAction,
    MoveWorkspaceToMonitorUpAction,
    MoveWorkspaceUpAction,
    OpenOverviewAction,
    PowerOffMonitorsAction,
    PowerOnMonitorsAction,
    QuitAction,
    ResetWindowHeightAction,
    ScreenshotAction,
    ScreenshotScreenAction,
    ScreenshotWindowAction,
    SetDynamicCastMonitorAction,
    SetDynamicCastWindowAction,
    SetWindowUrgentAction,
    ShowHotkeyOverlayAction,
    SpawnAction,
    SpawnShAction,
    SwapWindowLeftAction,
    SwapWindowRightAction,
    SwitchFocusBetweenFloatingAndTilingAction,
    SwitchPresetColumnWidthAction,
    SwitchPresetColumnWidthBackAction,
    SwitchPresetWindowHeightAction,
    SwitchPresetWindowHeightBackAction,
    SwitchPresetWindowWidthAction,
    SwitchPresetWindowWidthBackAction,
    ToggleColumnTabbedDisplayAction,
    ToggleKeyboardShortcutsInhibitAction,
    ToggleOverviewAction,
    ToggleWindowFloatingAction,
    ToggleWindowRuleOpacityAction,
    ToggleWindowUrgentAction,
    ToggleWindowedFullscreenAction,
    UnsetWindowUrgentAction,
)
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
from niri_pypc.types.generated.request import ActionRequest


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _wrap(variant: ActionValue) -> ActionRequest:
    """Wrap an action variant into a ready-to-send ActionRequest."""
    return ActionRequest(payload=Action(variant))


def _coerce_workspace_ref(
    ref: int | str | WorkspaceReferenceArg,
) -> WorkspaceReferenceArg:
    """Coerce a workspace reference shorthand to WorkspaceReferenceArg.

    - ``int`` -> Id variant (workspace IDs from niri's IPC responses)
    - ``str`` -> Name variant
    - ``WorkspaceReferenceArg`` -> pass-through
    """
    if isinstance(ref, WorkspaceReferenceArg):
        return ref
    if isinstance(ref, int):
        return WorkspaceReferenceArg(IdWorkspaceReferenceArg(payload=ref))
    if isinstance(ref, str):
        return WorkspaceReferenceArg(NameWorkspaceReferenceArg(payload=ref))
    raise TypeError(
        f"Expected int, str, or WorkspaceReferenceArg, got {type(ref).__name__}"
    )


def _coerce_optional_workspace_ref(
    ref: int | str | WorkspaceReferenceArg | None,
) -> WorkspaceReferenceArg | None:
    """Like _coerce_workspace_ref but allows None pass-through."""
    if ref is None:
        return None
    return _coerce_workspace_ref(ref)
```

## 4. actions.py — Nested Enum Helpers (14 functions)

### WorkspaceReferenceArg helpers (3)

```python
def workspace_by_id(id: int) -> WorkspaceReferenceArg:
    """Create a workspace reference by workspace ID."""
    return WorkspaceReferenceArg(IdWorkspaceReferenceArg(payload=id))

def workspace_by_index(index: int) -> WorkspaceReferenceArg:
    """Create a workspace reference by workspace index (0-based)."""
    return WorkspaceReferenceArg(IndexWorkspaceReferenceArg(payload=index))

def workspace_by_name(name: str) -> WorkspaceReferenceArg:
    """Create a workspace reference by workspace name."""
    return WorkspaceReferenceArg(NameWorkspaceReferenceArg(payload=name))
```

### SizeChange helpers (4)

```python
def size_set_fixed(value: int) -> SizeChange:
    """Set size to an exact pixel value."""
    return SizeChange(SetFixedSizeChange(payload=value))

def size_set_proportion(value: float) -> SizeChange:
    """Set size to a proportion of the available space."""
    return SizeChange(SetProportionSizeChange(payload=value))

def size_adjust_fixed(delta: int) -> SizeChange:
    """Adjust size by a fixed pixel delta."""
    return SizeChange(AdjustFixedSizeChange(payload=delta))

def size_adjust_proportion(delta: float) -> SizeChange:
    """Adjust size by a proportional delta."""
    return SizeChange(AdjustProportionSizeChange(payload=delta))
```

### PositionChange helpers (4)

```python
def pos_set_fixed(value: float) -> PositionChange:
    """Set position to an exact pixel value."""
    return PositionChange(SetFixedPositionChange(payload=value))

def pos_set_proportion(value: float) -> PositionChange:
    """Set position to a proportion of the available space."""
    return PositionChange(SetProportionPositionChange(payload=value))

def pos_adjust_fixed(delta: float) -> PositionChange:
    """Adjust position by a fixed pixel delta."""
    return PositionChange(AdjustFixedPositionChange(payload=delta))

def pos_adjust_proportion(delta: float) -> PositionChange:
    """Adjust position by a proportional delta."""
    return PositionChange(AdjustProportionPositionChange(payload=delta))
```

### LayoutSwitchTarget helpers (3)

```python
def layout_next() -> LayoutSwitchTarget:
    """Target the next keyboard layout."""
    return LayoutSwitchTarget(NextLayoutSwitchTarget())

def layout_prev() -> LayoutSwitchTarget:
    """Target the previous keyboard layout."""
    return LayoutSwitchTarget(PrevLayoutSwitchTarget())

def layout_index(index: int) -> LayoutSwitchTarget:
    """Target a keyboard layout by index."""
    return LayoutSwitchTarget(IndexLayoutSwitchTarget(payload=index))
```

## 5. actions.py — Builder Functions (137 functions)

Each builder is a thin wrapper: construct the action variant, pass to `_wrap()`, return `ActionRequest`.

### 5.1 Spawn (2 functions)

```python
def spawn(command: list[str]) -> ActionRequest:
    """Spawn a process with an explicit argument list."""
    return _wrap(SpawnAction(command=command))

def spawn_sh(command: str) -> ActionRequest:
    """Spawn a process via shell interpretation."""
    return _wrap(SpawnShAction(command=command))
```

### 5.2 Focus — Column (9 functions)

```python
def focus_column(index: int) -> ActionRequest:
    return _wrap(FocusColumnAction(index=index))

def focus_column_first() -> ActionRequest:
    return _wrap(FocusColumnFirstAction())

def focus_column_last() -> ActionRequest:
    return _wrap(FocusColumnLastAction())

def focus_column_left() -> ActionRequest:
    return _wrap(FocusColumnLeftAction())

def focus_column_left_or_last() -> ActionRequest:
    return _wrap(FocusColumnLeftOrLastAction())

def focus_column_right() -> ActionRequest:
    return _wrap(FocusColumnRightAction())

def focus_column_right_or_first() -> ActionRequest:
    return _wrap(FocusColumnRightOrFirstAction())

def focus_column_or_monitor_left() -> ActionRequest:
    return _wrap(FocusColumnOrMonitorLeftAction())

def focus_column_or_monitor_right() -> ActionRequest:
    return _wrap(FocusColumnOrMonitorRightAction())
```

### 5.3 Focus — Window (17 functions)

```python
def focus_window(id: int) -> ActionRequest:
    return _wrap(FocusWindowAction(id=id))

def focus_window_bottom() -> ActionRequest:
    return _wrap(FocusWindowBottomAction())

def focus_window_down() -> ActionRequest:
    return _wrap(FocusWindowDownAction())

def focus_window_down_or_column_left() -> ActionRequest:
    return _wrap(FocusWindowDownOrColumnLeftAction())

def focus_window_down_or_column_right() -> ActionRequest:
    return _wrap(FocusWindowDownOrColumnRightAction())

def focus_window_down_or_top() -> ActionRequest:
    return _wrap(FocusWindowDownOrTopAction())

def focus_window_in_column(index: int) -> ActionRequest:
    return _wrap(FocusWindowInColumnAction(index=index))

def focus_window_or_monitor_down() -> ActionRequest:
    return _wrap(FocusWindowOrMonitorDownAction())

def focus_window_or_monitor_up() -> ActionRequest:
    return _wrap(FocusWindowOrMonitorUpAction())

def focus_window_or_workspace_down() -> ActionRequest:
    return _wrap(FocusWindowOrWorkspaceDownAction())

def focus_window_or_workspace_up() -> ActionRequest:
    return _wrap(FocusWindowOrWorkspaceUpAction())

def focus_window_previous() -> ActionRequest:
    return _wrap(FocusWindowPreviousAction())

def focus_window_top() -> ActionRequest:
    return _wrap(FocusWindowTopAction())

def focus_window_up() -> ActionRequest:
    return _wrap(FocusWindowUpAction())

def focus_window_up_or_bottom() -> ActionRequest:
    return _wrap(FocusWindowUpOrBottomAction())

def focus_window_up_or_column_left() -> ActionRequest:
    return _wrap(FocusWindowUpOrColumnLeftAction())

def focus_window_up_or_column_right() -> ActionRequest:
    return _wrap(FocusWindowUpOrColumnRightAction())
```

### 5.4 Focus — Monitor (7 functions)

```python
def focus_monitor(output: str) -> ActionRequest:
    return _wrap(FocusMonitorAction(output=output))

def focus_monitor_down() -> ActionRequest:
    return _wrap(FocusMonitorDownAction())

def focus_monitor_left() -> ActionRequest:
    return _wrap(FocusMonitorLeftAction())

def focus_monitor_next() -> ActionRequest:
    return _wrap(FocusMonitorNextAction())

def focus_monitor_previous() -> ActionRequest:
    return _wrap(FocusMonitorPreviousAction())

def focus_monitor_right() -> ActionRequest:
    return _wrap(FocusMonitorRightAction())

def focus_monitor_up() -> ActionRequest:
    return _wrap(FocusMonitorUpAction())
```

### 5.5 Focus — Workspace (4 functions)

```python
def focus_workspace(reference: int | str | WorkspaceReferenceArg) -> ActionRequest:
    """Focus a workspace by ID (int), name (str), or explicit reference."""
    return _wrap(FocusWorkspaceAction(reference=_coerce_workspace_ref(reference)))

def focus_workspace_down() -> ActionRequest:
    return _wrap(FocusWorkspaceDownAction())

def focus_workspace_previous() -> ActionRequest:
    return _wrap(FocusWorkspacePreviousAction())

def focus_workspace_up() -> ActionRequest:
    return _wrap(FocusWorkspaceUpAction())
```

### 5.6 Focus — Layer (3 functions)

```python
def focus_floating() -> ActionRequest:
    return _wrap(FocusFloatingAction())

def focus_tiling() -> ActionRequest:
    return _wrap(FocusTilingAction())

def switch_focus_between_floating_and_tiling() -> ActionRequest:
    return _wrap(SwitchFocusBetweenFloatingAndTilingAction())
```

### 5.7 Window Management (11 functions)

```python
def center_window(id: int | None = None) -> ActionRequest:
    return _wrap(CenterWindowAction(id=id))

def close_window(id: int | None = None) -> ActionRequest:
    return _wrap(CloseWindowAction(id=id))

def fullscreen_window(id: int | None = None) -> ActionRequest:
    return _wrap(FullscreenWindowAction(id=id))

def maximize_window_to_edges(id: int | None = None) -> ActionRequest:
    return _wrap(MaximizeWindowToEdgesAction(id=id))

def reset_window_height(id: int | None = None) -> ActionRequest:
    return _wrap(ResetWindowHeightAction(id=id))

def toggle_window_floating(id: int | None = None) -> ActionRequest:
    return _wrap(ToggleWindowFloatingAction(id=id))

def toggle_window_rule_opacity(id: int | None = None) -> ActionRequest:
    return _wrap(ToggleWindowRuleOpacityAction(id=id))

def toggle_windowed_fullscreen(id: int | None = None) -> ActionRequest:
    return _wrap(ToggleWindowedFullscreenAction(id=id))

def set_window_urgent(id: int) -> ActionRequest:
    return _wrap(SetWindowUrgentAction(id=id))

def toggle_window_urgent(id: int) -> ActionRequest:
    return _wrap(ToggleWindowUrgentAction(id=id))

def unset_window_urgent(id: int) -> ActionRequest:
    return _wrap(UnsetWindowUrgentAction(id=id))
```

### 5.8 Window Sizing (6 functions)

```python
def set_window_height(change: SizeChange, id: int | None = None) -> ActionRequest:
    return _wrap(SetWindowHeightAction(change=change, id=id))

def set_window_width(change: SizeChange, id: int | None = None) -> ActionRequest:
    return _wrap(SetWindowWidthAction(change=change, id=id))

def switch_preset_window_height(id: int | None = None) -> ActionRequest:
    return _wrap(SwitchPresetWindowHeightAction(id=id))

def switch_preset_window_height_back(id: int | None = None) -> ActionRequest:
    return _wrap(SwitchPresetWindowHeightBackAction(id=id))

def switch_preset_window_width(id: int | None = None) -> ActionRequest:
    return _wrap(SwitchPresetWindowWidthAction(id=id))

def switch_preset_window_width_back(id: int | None = None) -> ActionRequest:
    return _wrap(SwitchPresetWindowWidthBackAction(id=id))
```

### 5.9 Window Movement (17 functions)

```python
def move_window_down() -> ActionRequest:
    return _wrap(MoveWindowDownAction())

def move_window_down_or_to_workspace_down() -> ActionRequest:
    return _wrap(MoveWindowDownOrToWorkspaceDownAction())

def move_window_to_floating(id: int | None = None) -> ActionRequest:
    return _wrap(MoveWindowToFloatingAction(id=id))

def move_window_to_monitor(output: str, id: int | None = None) -> ActionRequest:
    return _wrap(MoveWindowToMonitorAction(output=output, id=id))

def move_window_to_monitor_down() -> ActionRequest:
    return _wrap(MoveWindowToMonitorDownAction())

def move_window_to_monitor_left() -> ActionRequest:
    return _wrap(MoveWindowToMonitorLeftAction())

def move_window_to_monitor_next() -> ActionRequest:
    return _wrap(MoveWindowToMonitorNextAction())

def move_window_to_monitor_previous() -> ActionRequest:
    return _wrap(MoveWindowToMonitorPreviousAction())

def move_window_to_monitor_right() -> ActionRequest:
    return _wrap(MoveWindowToMonitorRightAction())

def move_window_to_monitor_up() -> ActionRequest:
    return _wrap(MoveWindowToMonitorUpAction())

def move_window_to_tiling(id: int | None = None) -> ActionRequest:
    return _wrap(MoveWindowToTilingAction(id=id))

def move_window_to_workspace(
    reference: int | str | WorkspaceReferenceArg,
    focus: bool = True,
    window_id: int | None = None,
) -> ActionRequest:
    """Move a window to a workspace. Follows focus by default."""
    return _wrap(MoveWindowToWorkspaceAction(
        reference=_coerce_workspace_ref(reference),
        focus=focus,
        window_id=window_id,
    ))

def move_window_to_workspace_down(focus: bool = True) -> ActionRequest:
    return _wrap(MoveWindowToWorkspaceDownAction(focus=focus))

def move_window_to_workspace_up(focus: bool = True) -> ActionRequest:
    return _wrap(MoveWindowToWorkspaceUpAction(focus=focus))

def move_window_up() -> ActionRequest:
    return _wrap(MoveWindowUpAction())

def move_window_up_or_to_workspace_up() -> ActionRequest:
    return _wrap(MoveWindowUpOrToWorkspaceUpAction())

def move_floating_window(
    x: PositionChange,
    y: PositionChange,
    id: int | None = None,
) -> ActionRequest:
    return _wrap(MoveFloatingWindowAction(x=x, y=y, id=id))
```

### 5.10 Column Management (15 functions)

```python
def center_column() -> ActionRequest:
    return _wrap(CenterColumnAction())

def center_visible_columns() -> ActionRequest:
    return _wrap(CenterVisibleColumnsAction())

def consume_or_expel_window_left(id: int | None = None) -> ActionRequest:
    return _wrap(ConsumeOrExpelWindowLeftAction(id=id))

def consume_or_expel_window_right(id: int | None = None) -> ActionRequest:
    return _wrap(ConsumeOrExpelWindowRightAction(id=id))

def consume_window_into_column() -> ActionRequest:
    return _wrap(ConsumeWindowIntoColumnAction())

def expand_column_to_available_width() -> ActionRequest:
    return _wrap(ExpandColumnToAvailableWidthAction())

def expel_window_from_column() -> ActionRequest:
    return _wrap(ExpelWindowFromColumnAction())

def maximize_column() -> ActionRequest:
    return _wrap(MaximizeColumnAction())

def set_column_display(display: ColumnDisplay) -> ActionRequest:
    return _wrap(SetColumnDisplayAction(display=display))

def set_column_width(change: SizeChange) -> ActionRequest:
    return _wrap(SetColumnWidthAction(change=change))

def switch_preset_column_width() -> ActionRequest:
    return _wrap(SwitchPresetColumnWidthAction())

def switch_preset_column_width_back() -> ActionRequest:
    return _wrap(SwitchPresetColumnWidthBackAction())

def toggle_column_tabbed_display() -> ActionRequest:
    return _wrap(ToggleColumnTabbedDisplayAction())

def swap_window_left() -> ActionRequest:
    return _wrap(SwapWindowLeftAction())

def swap_window_right() -> ActionRequest:
    return _wrap(SwapWindowRightAction())
```

### 5.11 Column Movement (17 functions)

```python
def move_column_left() -> ActionRequest:
    return _wrap(MoveColumnLeftAction())

def move_column_left_or_to_monitor_left() -> ActionRequest:
    return _wrap(MoveColumnLeftOrToMonitorLeftAction())

def move_column_right() -> ActionRequest:
    return _wrap(MoveColumnRightAction())

def move_column_right_or_to_monitor_right() -> ActionRequest:
    return _wrap(MoveColumnRightOrToMonitorRightAction())

def move_column_to_first() -> ActionRequest:
    return _wrap(MoveColumnToFirstAction())

def move_column_to_index(index: int) -> ActionRequest:
    return _wrap(MoveColumnToIndexAction(index=index))

def move_column_to_last() -> ActionRequest:
    return _wrap(MoveColumnToLastAction())

def move_column_to_monitor(output: str) -> ActionRequest:
    return _wrap(MoveColumnToMonitorAction(output=output))

def move_column_to_monitor_down() -> ActionRequest:
    return _wrap(MoveColumnToMonitorDownAction())

def move_column_to_monitor_left() -> ActionRequest:
    return _wrap(MoveColumnToMonitorLeftAction())

def move_column_to_monitor_next() -> ActionRequest:
    return _wrap(MoveColumnToMonitorNextAction())

def move_column_to_monitor_previous() -> ActionRequest:
    return _wrap(MoveColumnToMonitorPreviousAction())

def move_column_to_monitor_right() -> ActionRequest:
    return _wrap(MoveColumnToMonitorRightAction())

def move_column_to_monitor_up() -> ActionRequest:
    return _wrap(MoveColumnToMonitorUpAction())

def move_column_to_workspace(
    reference: int | str | WorkspaceReferenceArg,
    focus: bool = True,
) -> ActionRequest:
    """Move the focused column to a workspace. Follows focus by default."""
    return _wrap(MoveColumnToWorkspaceAction(
        reference=_coerce_workspace_ref(reference),
        focus=focus,
    ))

def move_column_to_workspace_down(focus: bool = True) -> ActionRequest:
    return _wrap(MoveColumnToWorkspaceDownAction(focus=focus))

def move_column_to_workspace_up(focus: bool = True) -> ActionRequest:
    return _wrap(MoveColumnToWorkspaceUpAction(focus=focus))
```

### 5.12 Workspace Management (12 functions)

```python
def set_workspace_name(
    name: str,
    workspace: int | str | WorkspaceReferenceArg | None = None,
) -> ActionRequest:
    """Set a workspace name. Targets the focused workspace if reference is None."""
    return _wrap(SetWorkspaceNameAction(
        name=name,
        workspace=_coerce_optional_workspace_ref(workspace),
    ))

def unset_workspace_name(
    reference: int | str | WorkspaceReferenceArg | None = None,
) -> ActionRequest:
    """Unset a workspace name. Targets the focused workspace if reference is None."""
    return _wrap(UnsetWorkspaceNameAction(
        reference=_coerce_optional_workspace_ref(reference),
    ))

def move_workspace_down() -> ActionRequest:
    return _wrap(MoveWorkspaceDownAction())

def move_workspace_to_index(
    index: int,
    reference: int | str | WorkspaceReferenceArg | None = None,
) -> ActionRequest:
    return _wrap(MoveWorkspaceToIndexAction(
        index=index,
        reference=_coerce_optional_workspace_ref(reference),
    ))

def move_workspace_to_monitor(
    output: str,
    reference: int | str | WorkspaceReferenceArg | None = None,
) -> ActionRequest:
    return _wrap(MoveWorkspaceToMonitorAction(
        output=output,
        reference=_coerce_optional_workspace_ref(reference),
    ))

def move_workspace_to_monitor_down() -> ActionRequest:
    return _wrap(MoveWorkspaceToMonitorDownAction())

def move_workspace_to_monitor_left() -> ActionRequest:
    return _wrap(MoveWorkspaceToMonitorLeftAction())

def move_workspace_to_monitor_next() -> ActionRequest:
    return _wrap(MoveWorkspaceToMonitorNextAction())

def move_workspace_to_monitor_previous() -> ActionRequest:
    return _wrap(MoveWorkspaceToMonitorPreviousAction())

def move_workspace_to_monitor_right() -> ActionRequest:
    return _wrap(MoveWorkspaceToMonitorRightAction())

def move_workspace_to_monitor_up() -> ActionRequest:
    return _wrap(MoveWorkspaceToMonitorUpAction())

def move_workspace_up() -> ActionRequest:
    return _wrap(MoveWorkspaceUpAction())
```

### 5.13 Layout (1 function)

```python
def switch_layout(layout: LayoutSwitchTarget) -> ActionRequest:
    return _wrap(SwitchLayoutAction(layout=layout))
```

### 5.14 Overview (3 functions)

```python
def close_overview() -> ActionRequest:
    return _wrap(CloseOverviewAction())

def open_overview() -> ActionRequest:
    return _wrap(OpenOverviewAction())

def toggle_overview() -> ActionRequest:
    return _wrap(ToggleOverviewAction())
```

### 5.15 Screenshot (3 functions)

```python
def screenshot(
    show_pointer: bool = False,
    path: str | None = None,
) -> ActionRequest:
    return _wrap(ScreenshotAction(show_pointer=show_pointer, path=path))

def screenshot_screen(
    show_pointer: bool = False,
    write_to_disk: bool = True,
    path: str | None = None,
) -> ActionRequest:
    return _wrap(ScreenshotScreenAction(
        show_pointer=show_pointer,
        write_to_disk=write_to_disk,
        path=path,
    ))

def screenshot_window(
    write_to_disk: bool = True,
    id: int | None = None,
    path: str | None = None,
) -> ActionRequest:
    return _wrap(ScreenshotWindowAction(
        write_to_disk=write_to_disk,
        id=id,
        path=path,
    ))
```

### 5.16 Monitor Power (2 functions)

```python
def power_off_monitors() -> ActionRequest:
    return _wrap(PowerOffMonitorsAction())

def power_on_monitors() -> ActionRequest:
    return _wrap(PowerOnMonitorsAction())
```

### 5.17 Screencast / Dynamic Cast (4 functions)

```python
def clear_dynamic_cast_target() -> ActionRequest:
    return _wrap(ClearDynamicCastTargetAction())

def set_dynamic_cast_monitor(output: str | None = None) -> ActionRequest:
    return _wrap(SetDynamicCastMonitorAction(output=output))

def set_dynamic_cast_window(id: int | None = None) -> ActionRequest:
    return _wrap(SetDynamicCastWindowAction(id=id))

def do_screen_transition(delay_ms: int | None = None) -> ActionRequest:
    return _wrap(DoScreenTransitionAction(delay_ms=delay_ms))
```

### 5.18 System (4 functions)

```python
def load_config_file() -> ActionRequest:
    return _wrap(LoadConfigFileAction())

def quit(skip_confirmation: bool = False) -> ActionRequest:
    """Quit niri. Shows confirmation dialog by default."""
    return _wrap(QuitAction(skip_confirmation=skip_confirmation))

def show_hotkey_overlay() -> ActionRequest:
    return _wrap(ShowHotkeyOverlayAction())

def toggle_keyboard_shortcuts_inhibit() -> ActionRequest:
    return _wrap(ToggleKeyboardShortcutsInhibitAction())
```

### Builder count verification

| Category | Count |
|----------|-------|
| Spawn | 2 |
| Focus — Column | 9 |
| Focus — Window | 17 |
| Focus — Monitor | 7 |
| Focus — Workspace | 4 |
| Focus — Layer | 3 |
| Window Management | 11 |
| Window Sizing | 6 |
| Window Movement | 17 |
| Column Management | 15 |
| Column Movement | 17 |
| Workspace Management | 12 |
| Layout | 1 |
| Overview | 3 |
| Screenshot | 3 |
| Monitor Power | 2 |
| Screencast / Dynamic Cast | 4 |
| System | 4 |
| **Total** | **137** |

Skipped (Tier 3 debug): `DebugToggleDamageAction`, `DebugToggleOpaqueRegionsAction`, `ToggleDebugTintAction` — 3 actions.

## 6. actions.py — `__all__` Definition

Place at the top of the file, after imports. Include all 14 nested enum helpers + 137 builders = **151 names**.

```python
__all__ = [
    # -- Nested enum helpers --
    # WorkspaceReferenceArg
    "workspace_by_id",
    "workspace_by_index",
    "workspace_by_name",
    # SizeChange
    "size_set_fixed",
    "size_set_proportion",
    "size_adjust_fixed",
    "size_adjust_proportion",
    # PositionChange
    "pos_set_fixed",
    "pos_set_proportion",
    "pos_adjust_fixed",
    "pos_adjust_proportion",
    # LayoutSwitchTarget
    "layout_next",
    "layout_prev",
    "layout_index",
    # -- Builders: Spawn --
    "spawn",
    "spawn_sh",
    # -- Builders: Focus — Column --
    "focus_column",
    "focus_column_first",
    "focus_column_last",
    "focus_column_left",
    "focus_column_left_or_last",
    "focus_column_right",
    "focus_column_right_or_first",
    "focus_column_or_monitor_left",
    "focus_column_or_monitor_right",
    # -- Builders: Focus — Window --
    "focus_window",
    "focus_window_bottom",
    "focus_window_down",
    "focus_window_down_or_column_left",
    "focus_window_down_or_column_right",
    "focus_window_down_or_top",
    "focus_window_in_column",
    "focus_window_or_monitor_down",
    "focus_window_or_monitor_up",
    "focus_window_or_workspace_down",
    "focus_window_or_workspace_up",
    "focus_window_previous",
    "focus_window_top",
    "focus_window_up",
    "focus_window_up_or_bottom",
    "focus_window_up_or_column_left",
    "focus_window_up_or_column_right",
    # -- Builders: Focus — Monitor --
    "focus_monitor",
    "focus_monitor_down",
    "focus_monitor_left",
    "focus_monitor_next",
    "focus_monitor_previous",
    "focus_monitor_right",
    "focus_monitor_up",
    # -- Builders: Focus — Workspace --
    "focus_workspace",
    "focus_workspace_down",
    "focus_workspace_previous",
    "focus_workspace_up",
    # -- Builders: Focus — Layer --
    "focus_floating",
    "focus_tiling",
    "switch_focus_between_floating_and_tiling",
    # -- Builders: Window Management --
    "center_window",
    "close_window",
    "fullscreen_window",
    "maximize_window_to_edges",
    "reset_window_height",
    "toggle_window_floating",
    "toggle_window_rule_opacity",
    "toggle_windowed_fullscreen",
    "set_window_urgent",
    "toggle_window_urgent",
    "unset_window_urgent",
    # -- Builders: Window Sizing --
    "set_window_height",
    "set_window_width",
    "switch_preset_window_height",
    "switch_preset_window_height_back",
    "switch_preset_window_width",
    "switch_preset_window_width_back",
    # -- Builders: Window Movement --
    "move_window_down",
    "move_window_down_or_to_workspace_down",
    "move_window_to_floating",
    "move_window_to_monitor",
    "move_window_to_monitor_down",
    "move_window_to_monitor_left",
    "move_window_to_monitor_next",
    "move_window_to_monitor_previous",
    "move_window_to_monitor_right",
    "move_window_to_monitor_up",
    "move_window_to_tiling",
    "move_window_to_workspace",
    "move_window_to_workspace_down",
    "move_window_to_workspace_up",
    "move_window_up",
    "move_window_up_or_to_workspace_up",
    "move_floating_window",
    # -- Builders: Column Management --
    "center_column",
    "center_visible_columns",
    "consume_or_expel_window_left",
    "consume_or_expel_window_right",
    "consume_window_into_column",
    "expand_column_to_available_width",
    "expel_window_from_column",
    "maximize_column",
    "set_column_display",
    "set_column_width",
    "switch_preset_column_width",
    "switch_preset_column_width_back",
    "toggle_column_tabbed_display",
    "swap_window_left",
    "swap_window_right",
    # -- Builders: Column Movement --
    "move_column_left",
    "move_column_left_or_to_monitor_left",
    "move_column_right",
    "move_column_right_or_to_monitor_right",
    "move_column_to_first",
    "move_column_to_index",
    "move_column_to_last",
    "move_column_to_monitor",
    "move_column_to_monitor_down",
    "move_column_to_monitor_left",
    "move_column_to_monitor_next",
    "move_column_to_monitor_previous",
    "move_column_to_monitor_right",
    "move_column_to_monitor_up",
    "move_column_to_workspace",
    "move_column_to_workspace_down",
    "move_column_to_workspace_up",
    # -- Builders: Workspace Management --
    "set_workspace_name",
    "unset_workspace_name",
    "move_workspace_down",
    "move_workspace_to_index",
    "move_workspace_to_monitor",
    "move_workspace_to_monitor_down",
    "move_workspace_to_monitor_left",
    "move_workspace_to_monitor_next",
    "move_workspace_to_monitor_previous",
    "move_workspace_to_monitor_right",
    "move_workspace_to_monitor_up",
    "move_workspace_up",
    # -- Builders: Layout --
    "switch_layout",
    # -- Builders: Overview --
    "close_overview",
    "open_overview",
    "toggle_overview",
    # -- Builders: Screenshot --
    "screenshot",
    "screenshot_screen",
    "screenshot_window",
    # -- Builders: Monitor Power --
    "power_off_monitors",
    "power_on_monitors",
    # -- Builders: Screencast / Dynamic Cast --
    "clear_dynamic_cast_target",
    "set_dynamic_cast_monitor",
    "set_dynamic_cast_window",
    "do_screen_transition",
    # -- Builders: System --
    "load_config_file",
    "quit",
    "show_hotkey_overlay",
    "toggle_keyboard_shortcuts_inhibit",
]
```

## 7. Package Root Update

Add one line to `src/niri_pypc/__init__.py`:

```python
from niri_pypc import actions  # noqa: F401
```

This enables `from niri_pypc import actions` and `from niri_pypc.actions import spawn`.

## 8. tests/test_actions.py

Run with: `PYTHONPATH=src pytest tests/test_actions.py -v`

### 8.1 Test structure

```python
"""Tests for niri_pypc.actions builder functions."""

from __future__ import annotations

import pytest

from niri_pypc.actions import (
    # Internals (import for testing)
    _coerce_workspace_ref,
    _coerce_optional_workspace_ref,
    # Nested enum helpers
    workspace_by_id, workspace_by_index, workspace_by_name,
    size_set_fixed, size_set_proportion, size_adjust_fixed, size_adjust_proportion,
    pos_set_fixed, pos_set_proportion, pos_adjust_fixed, pos_adjust_proportion,
    layout_next, layout_prev, layout_index,
    # Builders (import all)
    spawn, spawn_sh,
    focus_column, focus_column_first, focus_column_last,
    # ... (all 137)
    quit,
)
import niri_pypc.actions as actions_module
from niri_pypc.types.generated.action import Action
from niri_pypc.types.generated.models import (
    ColumnDisplay,
    IdWorkspaceReferenceArg,
    IndexWorkspaceReferenceArg,
    NameWorkspaceReferenceArg,
    WorkspaceReferenceArg,
    SizeChange, SetFixedSizeChange,
    PositionChange,
    LayoutSwitchTarget, NextLayoutSwitchTarget,
)
from niri_pypc.types.generated.request import ActionRequest, Request
```

### 8.2 Test category 1: Nested enum helpers

```python
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

    # ... similar for other 3


class TestPositionChangeHelpers:
    def test_pos_set_fixed(self):
        pc = pos_set_fixed(100.0)
        assert isinstance(pc, PositionChange)
        # ...


class TestLayoutSwitchTargetHelpers:
    def test_layout_next(self):
        lt = layout_next()
        assert isinstance(lt, LayoutSwitchTarget)
        assert isinstance(lt.root, NextLayoutSwitchTarget)
```

### 8.3 Test category 2: Workspace coercion

```python
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
```

### 8.4 Test category 3: Return type assertions (parametrized)

```python
# Complete list of (function, args) pairs for all 137 builders
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
    # ... all remaining builders with minimal valid args ...
    # System
    (quit, ()),
    (show_hotkey_overlay, ()),
    (toggle_keyboard_shortcuts_inhibit, ()),
]


@pytest.mark.parametrize("fn,args", ALL_BUILDERS, ids=lambda x: x.__name__ if callable(x) else str(x))
def test_returns_action_request(fn, args):
    result = fn(*args)
    assert isinstance(result, ActionRequest)
    assert isinstance(result.payload, Action)
```

**Important:** The `ALL_BUILDERS` list must include all 137 `(function, args)` tuples. Use minimal valid arguments for each function (e.g., `(focus_window, (1,))`, `(quit, ())`). For builders requiring nested enum params, use the helpers: `(set_column_width, (size_set_fixed(800),))`.

### 8.5 Test category 4: Wire-format round-trip

```python
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
```

### 8.6 Test category 5: Default value assertions

```python
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
```

### 8.7 Test category 6: Completeness meta-test

```python
SKIP_DEBUG = {"DebugToggleDamage", "DebugToggleOpaqueRegions", "ToggleDebugTint"}


def test_all_non_debug_actions_have_builders():
    """Every non-debug action variant should be constructible via a builder."""
    variant_wire_names = {
        v.__niri_wire_name__
        for v in Action.__niri_variants__
        if v.__niri_wire_name__ not in SKIP_DEBUG
    }
    # ALL_BUILDERS should cover exactly 137 functions (one per non-debug variant)
    assert len(ALL_BUILDERS) == len(variant_wire_names) == 137


def test_all_exports_match():
    """__all__ contains exactly the public functions."""
    exported = set(actions_module.__all__)
    # 14 nested enum helpers + 137 builders = 151
    assert len(exported) == 151
```

## 9. Validation Checklist

Before submitting the PR, verify:

- [ ] `actions.py` imports compile: `python -c "from niri_pypc.actions import spawn"`
- [ ] `len(__all__) == 151`
- [ ] All tests pass: `PYTHONPATH=src pytest tests/test_actions.py -v`
- [ ] Completeness meta-test passes (137 builders, 137 non-debug variants)
- [ ] Wire-format tests cover all Tier 1 actions (nested enum params)
- [ ] Default value tests cover `focus`, `skip_confirmation`, `show_pointer`, `write_to_disk`
- [ ] No debug actions (`DebugToggleDamage`, `DebugToggleOpaqueRegions`, `ToggleDebugTint`) in builders
- [ ] `_wrap` and `_coerce_workspace_ref` are NOT in `__all__`
- [ ] Package root import works: `from niri_pypc import actions`
- [ ] No generated types re-exported from `actions.py` (users import those from `types.generated`)

### Cross-reference check

Every `*Action` class imported from `action.py` must match an actual class in the generated file. Verify by running:

```bash
# Count action classes in generated file (should be 140)
grep -c "^class.*Action(ProtocolVariant):" src/niri_pypc/types/generated/action.py

# Count builder functions in actions.py (should be 137)
grep -c "^def [a-z]" src/niri_pypc/actions.py
# (subtract 4 for _wrap, _coerce_workspace_ref, _coerce_optional_workspace_ref, and any helpers)
```
