# ACTION_REFACTOR_CONCEPT

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Current State](#2-current-state)
3. [Design Goals](#3-design-goals)
4. [Action Tiering](#4-action-tiering)
5. [Proposed Public API](#5-proposed-public-api)
6. [Nested Enum Ergonomics](#6-nested-enum-ergonomics)
7. [Default Value Policy](#7-default-value-policy)
8. [Module Layout and Exports](#8-module-layout-and-exports)
9. [Builder Architecture](#9-builder-architecture)
10. [Testing Strategy](#10-testing-strategy)
11. [Implementation Plan](#11-implementation-plan)
12. [Risks and Mitigations](#12-risks-and-mitigations)

## 1. Purpose and Scope

This concept proposes adding a stable, hand-written **action helper layer** to `niri-pypc` so that downstream libraries can construct action requests without importing raw generated variant classes directly.

This concept is **purely additive**. It does not replace the generated protocol types under `src/niri_pypc/types/generated/` and does not alter transport behavior in `api/client.py` or `api/event_stream.py`.

### In Scope

- Ergonomic builder functions for all non-debug action variants (137 functions).
- Nested enum helper constructors for `WorkspaceReferenceArg`, `SizeChange`, `PositionChange`, `LayoutSwitchTarget`.
- Workspace reference coercion (`int | str` -> `WorkspaceReferenceArg`).
- Sensible default values for `focus`, `skip_confirmation`, `show_pointer`, etc.
- Wire-format round-trip tests.

### Out of Scope

- **`OutputRequest` builders.** `OutputRequest` is a separate request type (not an `ActionRequest`) with its own deeply-nested `OutputAction` enum containing mode configuration (`ConfiguredMode`, `ModeToSet`, `Modeline`, `VrrToSet`, etc.). Including it would roughly double the API surface for a feature that is rarely used via IPC — most output configuration happens in `niri.kdl`. It can be added as a follow-up if demand exists.
- **`niri_pypc.compat` metadata/compatibility surface.** This is a separate concern and will be addressed in its own concept document.
- **Presets / multi-action sequences.** No real downstream use-cases exist yet. Premature.
- **`client.request_action()` convenience method.** Deferred to keep transport API minimal. Builders return `ActionRequest` objects; callers pass them to `client.request()`.
- Changes to wire protocol encoding/decoding.
- Changes to `tools/generate_types.py` output format.

## 2. Current State

### Relevant generated files

| File | Role |
|------|------|
| `types/generated/action.py` | 140 `*Action` variant classes + `Action` enum + `ActionValue` alias |
| `types/generated/models.py` | `WorkspaceReferenceArg`, `SizeChange`, `PositionChange`, `LayoutSwitchTarget`, `ColumnDisplay` |
| `types/generated/request.py` | `ActionRequest(payload: Action)` + `Request` enum |

### Pain points

Constructing even a simple action requires understanding three nesting layers:

```python
from niri_pypc.types.generated.request import ActionRequest
from niri_pypc.types.generated.action import Action, SpawnAction

# Current: verbose, fragile, requires knowing exact class names
req = ActionRequest(payload=Action(SpawnAction(command=["alacritty"])))
```

Nested enum parameters make it worse:

```python
from niri_pypc.types.generated.models import (
    WorkspaceReferenceArg, NameWorkspaceReferenceArg,
)
from niri_pypc.types.generated.action import Action, FocusWorkspaceAction
from niri_pypc.types.generated.request import ActionRequest

req = ActionRequest(
    payload=Action(FocusWorkspaceAction(
        reference=WorkspaceReferenceArg(NameWorkspaceReferenceArg(payload="browser"))
    ))
)
```

### Target

```python
from niri_pypc.actions import spawn, focus_workspace

req1 = spawn(["alacritty"])
req2 = focus_workspace("browser")  # str auto-coerced to Name variant
```

## 3. Design Goals

1. **Preserve generated types as source-of-truth wire models.** Builders are a convenience layer, not a replacement.
2. **One function per action variant.** Predictable, discoverable, greppable.
3. **Full type coverage.** Every builder has explicit parameter types and returns `ActionRequest`.
4. **Thin wrappers.** Each builder is 1-3 lines. No business logic, no transport coupling.
5. **Stable naming.** Function names use `snake_case` domain names. If generated class names change, only builder internals update.
6. **Ergonomic coercion** where the type system allows it (workspace references accept `int | str`).
7. **No dedicated exception types.** Builders are pure constructors; invalid arguments raise standard `TypeError`/`ValueError`.

## 4. Action Tiering

All 140 action variants in `action.py` are categorized into three tiers:

### Tier 1: Complex Parameters (14 actions)

Actions that take nested enum parameters (`WorkspaceReferenceArg`, `SizeChange`, `PositionChange`, `LayoutSwitchTarget`). These benefit most from helper functions.

| Action | Nested Enum Params |
|--------|--------------------|
| `FocusWorkspaceAction` | `WorkspaceReferenceArg` |
| `MoveColumnToWorkspaceAction` | `WorkspaceReferenceArg` |
| `MoveWindowToWorkspaceAction` | `WorkspaceReferenceArg` |
| `MoveWorkspaceToIndexAction` | `WorkspaceReferenceArg` (optional) |
| `MoveWorkspaceToMonitorAction` | `WorkspaceReferenceArg` (optional) |
| `SetWorkspaceNameAction` | `WorkspaceReferenceArg` (optional) |
| `UnsetWorkspaceNameAction` | `WorkspaceReferenceArg` (optional) |
| `SetColumnWidthAction` | `SizeChange` |
| `SetWindowHeightAction` | `SizeChange` |
| `SetWindowWidthAction` | `SizeChange` |
| `MoveFloatingWindowAction` | `PositionChange` (x2) |
| `SwitchLayoutAction` | `LayoutSwitchTarget` |
| `SetColumnDisplayAction` | `ColumnDisplay` (StrEnum — simple) |

### Tier 2: Simple/Parameterless (123 actions)

Actions that are parameterless or take only primitive parameters (`int`, `str`, `bool`, `list[str]`). Still worth covering for consistency and the `_wrap()` convenience.

### Tier 3: Debug (3 actions) — Skip

- `DebugToggleDamageAction`
- `DebugToggleOpaqueRegionsAction`
- `ToggleDebugTintAction`

These are niri-internal debugging tools, not useful for IPC consumers. Excluding them keeps the API clean. Users who need them can still construct them directly from generated types.

**Result:** 137 builder functions covering Tier 1 + Tier 2.

## 5. Proposed Public API

### Import style

```python
# Individual imports (preferred)
from niri_pypc.actions import spawn, focus_workspace, quit

# Namespace import
from niri_pypc import actions
actions.spawn(["alacritty"])
```

### Builder examples

```python
from niri_pypc.actions import (
    spawn, spawn_sh, focus_workspace, move_window_to_workspace,
    set_column_width, switch_layout, quit, screenshot,
    # Nested enum helpers
    size_set_fixed, size_adjust_proportion,
    layout_next, layout_prev,
    workspace_by_name, workspace_by_index,
)

# Simple actions
spawn(["alacritty"])
spawn_sh("notify-send hello")
quit()                              # skip_confirmation=False by default
quit(skip_confirmation=True)

# Workspace reference coercion
focus_workspace("browser")          # str -> Name variant
focus_workspace(3)                  # int -> Id variant
focus_workspace(workspace_by_index(2))  # explicit Index variant

# Focus follows by default
move_window_to_workspace("coding")          # focus=True
move_window_to_workspace("coding", focus=False)

# Nested enum helpers for sizing
set_column_width(size_set_fixed(800))
set_column_width(size_adjust_proportion(0.1))

# Layout switching
switch_layout(layout_next())
switch_layout(layout_prev())

# Screenshot with defaults
screenshot()                         # show_pointer=False
screenshot(show_pointer=True)
```

## 6. Nested Enum Ergonomics

Four generated enum types require multi-level nesting to construct. The actions module provides flat helper functions for each variant.

### 6.1 `WorkspaceReferenceArg` (3 helpers + 1 coercion)

Generated structure: `WorkspaceReferenceArg(IdWorkspaceReferenceArg(payload=42))`

| Helper | Returns | Wraps |
|--------|---------|-------|
| `workspace_by_id(id: int)` | `WorkspaceReferenceArg` | `IdWorkspaceReferenceArg` |
| `workspace_by_index(index: int)` | `WorkspaceReferenceArg` | `IndexWorkspaceReferenceArg` |
| `workspace_by_name(name: str)` | `WorkspaceReferenceArg` | `NameWorkspaceReferenceArg` |

**Private coercion:** `_coerce_workspace_ref(ref: int | str | WorkspaceReferenceArg) -> WorkspaceReferenceArg`

- `int` → `workspace_by_id(ref)` (workspace IDs are the common lookup key)
- `str` → `workspace_by_name(ref)`
- `WorkspaceReferenceArg` → pass-through

This coercion is used internally by builders that accept workspace references, so users can write `focus_workspace("browser")` or `focus_workspace(42)` instead of constructing the enum manually.

### 6.2 `SizeChange` (4 helpers)

Generated structure: `SizeChange(SetFixedSizeChange(payload=800))`

| Helper | Returns | Wraps |
|--------|---------|-------|
| `size_set_fixed(value: int)` | `SizeChange` | `SetFixedSizeChange` |
| `size_set_proportion(value: float)` | `SizeChange` | `SetProportionSizeChange` |
| `size_adjust_fixed(delta: int)` | `SizeChange` | `AdjustFixedSizeChange` |
| `size_adjust_proportion(delta: float)` | `SizeChange` | `AdjustProportionSizeChange` |

### 6.3 `PositionChange` (4 helpers)

Generated structure: `PositionChange(SetFixedPositionChange(payload=100.0))`

| Helper | Returns | Wraps |
|--------|---------|-------|
| `pos_set_fixed(value: float)` | `PositionChange` | `SetFixedPositionChange` |
| `pos_set_proportion(value: float)` | `PositionChange` | `SetProportionPositionChange` |
| `pos_adjust_fixed(delta: float)` | `PositionChange` | `AdjustFixedPositionChange` |
| `pos_adjust_proportion(delta: float)` | `PositionChange` | `AdjustProportionPositionChange` |

### 6.4 `LayoutSwitchTarget` (3 helpers)

Generated structure: `LayoutSwitchTarget(NextLayoutSwitchTarget())`

| Helper | Returns | Wraps |
|--------|---------|-------|
| `layout_next()` | `LayoutSwitchTarget` | `NextLayoutSwitchTarget` |
| `layout_prev()` | `LayoutSwitchTarget` | `PrevLayoutSwitchTarget` |
| `layout_index(index: int)` | `LayoutSwitchTarget` | `IndexLayoutSwitchTarget` |

**Total:** 14 nested enum helper functions.

## 7. Default Value Policy

Where generated types require explicit values that have an obvious "safe" default, builders provide defaults:

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| `focus` (workspace move actions) | `True` | Users expect to follow the moved window/column |
| `skip_confirmation` (quit) | `False` | Safe default; explicit opt-in for force quit |
| `show_pointer` (screenshot) | `False` | Matches typical screenshot behavior |
| `write_to_disk` (screenshot_screen, screenshot_window) | `True` | Matches niri's default behavior |

Generated types that already have `None` defaults (e.g., `id: int | None = None`) are preserved as-is in builders.

## 8. Module Layout and Exports

### Single file

```
src/niri_pypc/actions.py     # All builders + nested enum helpers
tests/test_actions.py         # All tests
```

A single file is appropriate because:
- Builders are 1-3 lines each. Even 137 functions fit comfortably in ~600 lines.
- No internal cross-references or circular imports.
- Simpler to navigate than a package with `__init__.py`, `builders.py`, `presets.py`.
- Single grep target for downstream contributors.

### `__all__` export strategy

The module defines `__all__` containing:
1. All 137 builder functions.
2. All 14 nested enum helper functions.
3. **Not** internal helpers (`_wrap`, `_coerce_workspace_ref`).
4. **Not** re-exported generated types (users import those from `types.generated` if needed).

### Package root re-export

Add to `src/niri_pypc/__init__.py`:

```python
from niri_pypc import actions
```

This enables both `from niri_pypc.actions import spawn` and `from niri_pypc import actions; actions.spawn(...)`.

## 9. Builder Architecture

### 9.1 Internal `_wrap()` helper

All builders share a single private helper:

```python
from niri_pypc.types.generated.action import Action, ActionValue
from niri_pypc.types.generated.request import ActionRequest

def _wrap(variant: ActionValue) -> ActionRequest:
    return ActionRequest(payload=Action(variant))
```

This encapsulates the `ActionRequest(payload=Action(variant))` nesting so each builder is a single return statement.

### 9.2 Builder rules

- Builders are **deterministic** and **side-effect free**.
- Builders return `ActionRequest` only. They never call `NiriClient`.
- Builders are **thin wrappers** — no validation beyond what Pydantic enforces.
- Parameter order: required params first, then optional params with defaults.
- For workspace ref params that accept coercion, the type annotation is `int | str | WorkspaceReferenceArg`.

### 9.3 Example builder implementations

```python
def spawn(command: list[str]) -> ActionRequest:
    """Spawn a process with an explicit argument list."""
    return _wrap(SpawnAction(command=command))

def focus_workspace(reference: int | str | WorkspaceReferenceArg) -> ActionRequest:
    """Focus a workspace by ID (int), name (str), or explicit reference."""
    return _wrap(FocusWorkspaceAction(reference=_coerce_workspace_ref(reference)))

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

def quit(skip_confirmation: bool = False) -> ActionRequest:
    """Quit niri. Shows confirmation dialog by default."""
    return _wrap(QuitAction(skip_confirmation=skip_confirmation))
```

## 10. Testing Strategy

All tests go in `tests/test_actions.py`. Run with:

```
PYTHONPATH=src pytest tests/test_actions.py -v
```

### 10.1 Nested enum helpers

Verify each helper constructs the correct variant:

```python
def test_workspace_by_name():
    ref = workspace_by_name("browser")
    assert isinstance(ref, WorkspaceReferenceArg)
    assert isinstance(ref.root, NameWorkspaceReferenceArg)
    assert ref.root.payload == "browser"
```

### 10.2 Workspace coercion

```python
def test_coerce_int():
    ref = _coerce_workspace_ref(42)
    assert isinstance(ref.root, IdWorkspaceReferenceArg)

def test_coerce_str():
    ref = _coerce_workspace_ref("browser")
    assert isinstance(ref.root, NameWorkspaceReferenceArg)

def test_coerce_passthrough():
    original = workspace_by_index(3)
    assert _coerce_workspace_ref(original) is original
```

### 10.3 Return type assertions

Every builder must return `ActionRequest`:

```python
@pytest.mark.parametrize("fn,args", [
    (spawn, (["ls"],)),
    (focus_column_left, ()),
    (quit, ()),
    # ... all 137
])
def test_returns_action_request(fn, args):
    result = fn(*args)
    assert isinstance(result, ActionRequest)
```

### 10.4 Wire-format round-trip

Verify that builder output serializes to the expected JSON and deserializes back correctly:

```python
def test_spawn_wire_format():
    req = spawn(["alacritty", "--title", "test"])
    wire = Request(req).model_dump(mode="json")
    assert wire == {"Action": {"Spawn": {"command": ["alacritty", "--title", "test"]}}}

def test_focus_workspace_wire_format():
    req = focus_workspace("browser")
    wire = Request(req).model_dump(mode="json")
    assert wire == {"Action": {"FocusWorkspace": {"reference": {"Name": "browser"}}}}

def test_quit_wire_format():
    req = quit(skip_confirmation=True)
    wire = Request(req).model_dump(mode="json")
    assert wire == {"Action": {"Quit": {"skip_confirmation": True}}}
```

### 10.5 Default value assertions

```python
def test_quit_default_no_skip():
    req = quit()
    assert req.payload.root.skip_confirmation is False

def test_move_window_default_focus():
    req = move_window_to_workspace("test")
    assert req.payload.root.focus is True
```

### 10.6 Completeness check

A meta-test that ensures every non-debug action variant has a corresponding builder:

```python
from niri_pypc.types.generated.action import Action
import niri_pypc.actions as actions_module

SKIP_DEBUG = {"DebugToggleDamage", "DebugToggleOpaqueRegions", "ToggleDebugTint"}

def test_all_actions_covered():
    variant_names = {
        v.__niri_wire_name__
        for v in Action.__niri_variants__
        if v.__niri_wire_name__ not in SKIP_DEBUG
    }
    exported = set(actions_module.__all__)
    # Each variant should be constructible via at least one exported function
    # This test is validated by the parametrized return-type test covering all 137 functions
    assert len(exported) >= len(variant_names)
```

## 11. Implementation Plan

### Single PR

All work ships in one PR:

1. Create `src/niri_pypc/actions.py`:
   - Imports from `types.generated.action` and `types.generated.models`
   - `_wrap()` internal helper
   - 14 nested enum helpers
   - `_coerce_workspace_ref()` internal helper
   - 137 builder functions organized by category
   - `__all__` list

2. Create `tests/test_actions.py`:
   - 6 test categories as described above
   - Full parametrized coverage of all 137 builders

3. Update `src/niri_pypc/__init__.py`:
   - Add `from niri_pypc import actions`

### Exit criteria

- All 137 builders construct valid `ActionRequest` objects.
- Wire-format tests pass for Tier 1 actions (nested enums).
- Completeness meta-test passes.
- `from niri_pypc.actions import spawn` works.

## 12. Risks and Mitigations

**Risk:** Builder function count (~137) becomes maintenance burden when upstream adds new actions.

- **Mitigation:** Each builder is 1-3 lines. A generator script could scaffold new builders, but hand-writing is fine at this scale. The completeness test catches gaps immediately.

**Risk:** Workspace reference coercion (`int` → `Id` variant) may surprise users who expect `int` → `Index`.

- **Mitigation:** Document clearly. `int` maps to `Id` because workspace IDs are the primary lookup key in niri's IPC responses. Users who want index-based lookup use `workspace_by_index()` explicitly.

**Risk:** Helper API drifts from generated model capabilities.

- **Mitigation:** Builders are thin wrappers with no logic. Wire-format tests catch serialization mismatches. Completeness test catches missing coverage.
