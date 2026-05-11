# NIRI_PYPC_REFACTORING_GUIDE

## Purpose

This document is a complete, step-by-step implementation guide for refactoring the `niri-pypc` library. It is written for an implementer who has access to the codebase and can execute each step mechanically. Every change is described with enough detail to implement without ambiguity.

Backwards compatibility is explicitly **not** a constraint. The only goal is the cleanest, most correct codebase possible.

---

## Orientation

### Repository layout

```
niri-pypc/
├── schema/
│   ├── upstream-pin.toml             # Pins niri-ipc = "25.11"
│   ├── exported/                     # Raw JSON Schema from Rust exporter
│   │   ├── action.schema.json
│   │   ├── event.schema.json
│   │   ├── reply.schema.json
│   │   └── request.schema.json
│   └── ir/
│       └── niri-ipc-ir.json          # Normalized intermediate representation
├── tools/
│   ├── normalize_ir.py               # JSON Schema → IR
│   ├── generate_types.py             # IR → Python Pydantic models
│   └── verify_generated.py           # (to be created/fixed) Diff check
├── src/niri_pypc/
│   ├── __init__.py                   # Public re-exports
│   ├── _version.py
│   ├── errors.py                     # Error hierarchy
│   ├── config.py                     # NiriConfig, BackpressureMode
│   ├── api/
│   │   ├── client.py                 # NiriClient
│   │   ├── event_stream.py           # NiriEventStream
│   │   └── bundle.py                 # NiriConnectionBundle
│   ├── runtime/
│   │   └── lifecycle.py              # LifecycleManager (used by event_stream)
│   ├── transport/
│   │   ├── connection.py             # UnixConnection
│   │   └── framing.py               # encode_frame / decode_frame
│   └── types/
│       ├── __init__.py
│       ├── codec.py                  # Externally-tagged enum encode/decode
│       └── generated/                # AUTO-GENERATED — do not edit by hand
│           ├── __init__.py
│           ├── _metadata.py
│           ├── models.py
│           ├── action.py
│           ├── event.py
│           ├── request.py
│           └── reply.py
└── tests/
    ├── conftest.py
    ├── types/
    ├── transport/
    ├── api/
    ├── integration/
    └── live/
```

### Data flow

```
Rust niri-ipc crate
  → schema_exporter (Rust binary via schemars)
  → schema/exported/*.schema.json
  → tools/normalize_ir.py
  → schema/ir/niri-ipc-ir.json
  → tools/generate_types.py
  → src/niri_pypc/types/generated/
```

### Wire format

niri uses Rust serde externally-tagged enums over newline-delimited JSON on a Unix socket:
- Unit variants: `"VariantName"` (bare JSON string)
- Payload variants: `{"VariantName": <payload>}` (single-key JSON object)
- Reply is `{"Ok": <Response>}` or `{"Err": "message"}`

---

## Phase 1: Fix the schema → IR → generation pipeline

This is the most important phase. The library's core promise is faithful, typed protocol models. The current pipeline loses type information for arrays, maps, nullable refs, and fixed-length tuples.

### Step 1.1: Rewrite `canonical_type()` in `tools/normalize_ir.py`

**Problem**: The current function checks `schema["type"]` on line 37 and returns a primitive immediately, before checking `items`, `additionalProperties`, `prefixItems`, or `anyOf`. This causes arrays to become `array<ref:Unknown>`, maps to become `object`, and nullable refs to be misclassified.

**Current code** (lines 28–61):

```python
def canonical_type(schema: dict, defs: dict) -> str:
    raw = schema.get("type")
    if isinstance(raw, list):
        if "null" in raw:
            inner = [t for t in raw if t != "null"][0]
            inner_type = _primitive_type(inner)
            return f"option<{inner_type}>" if inner_type else "option<ref:Unknown>"
        return _primitive_type(raw[0])
    if raw:
        return _primitive_type(raw)       # ← RETURNS TOO EARLY
    # ... $ref, anyOf, items, additionalProperties checks below never reached
    #     when "type" key is present
```

**Required rewrite**: Replace the entire `canonical_type()` function with a shape-first implementation that checks in the correct precedence order:

```python
def canonical_type(schema: dict, defs: dict) -> str:
    """Convert JSON Schema type notation to canonical IR type string.

    Precedence order:
    1. $ref
    2. anyOf (nullable unions)
    3. arrays with items
    4. arrays with prefixItems (fixed-length tuples)
    5. objects with additionalProperties (maps)
    6. nullable type arrays like ["string", "null"]
    7. plain primitives
    """

    # 1. Direct $ref — always takes precedence
    if "$ref" in schema:
        return f"ref:{resolve_ref(schema['$ref'])}"

    # 2. anyOf — typically nullable refs: [{"$ref": "..."}, {"type": "null"}]
    if "anyOf" in schema:
        variants = schema["anyOf"]
        non_null = [v for v in variants if v.get("type") != "null"]
        has_null = len(non_null) < len(variants)
        if non_null:
            inner = canonical_type(non_null[0], defs)
            return f"option<{inner}>" if has_null else inner
        return "option<ref:Unknown>"

    raw_type = schema.get("type")

    # 3. Handle nullable type arrays: {"type": ["array", "null"], ...}
    if isinstance(raw_type, list):
        non_null_types = [t for t in raw_type if t != "null"]
        has_null = len(non_null_types) < len(raw_type)
        if not non_null_types:
            return "option<ref:Unknown>"
        # Recurse with the non-null type to pick up items/additionalProperties/prefixItems
        inner_schema = dict(schema)
        inner_schema["type"] = non_null_types[0]
        inner = canonical_type(inner_schema, defs)
        return f"option<{inner}>" if has_null else inner

    # 4. Arrays with typed items
    if raw_type == "array" or (raw_type is None and "items" in schema):
        if "items" in schema and isinstance(schema["items"], dict):
            inner = canonical_type(schema["items"], defs)
            return f"array<{inner}>"
        if "prefixItems" in schema:
            return _normalize_prefix_items(schema, defs)
        return "array<ref:Unknown>"

    # 5. Arrays with prefixItems but no explicit type
    if "prefixItems" in schema:
        return _normalize_prefix_items(schema, defs)

    # 6. Objects with additionalProperties (maps)
    if raw_type == "object" or (raw_type is None and "additionalProperties" in schema):
        if "additionalProperties" in schema and isinstance(
            schema["additionalProperties"], dict
        ):
            val = canonical_type(schema["additionalProperties"], defs)
            return f"map<string,{val}>"
        if "properties" in schema and schema["properties"]:
            # Real struct — handled elsewhere (extract_fields)
            return "object"
        if not schema.get("properties"):
            # Empty object (e.g., Rust unit struct serialized as {})
            return "object"

    # 7. Plain primitives
    if raw_type:
        return _primitive_type(raw_type)

    # 8. Bare items/additionalProperties without type key
    if "items" in schema and isinstance(schema["items"], dict):
        inner = canonical_type(schema["items"], defs)
        return f"array<{inner}>"

    if "additionalProperties" in schema and isinstance(
        schema["additionalProperties"], dict
    ):
        val = canonical_type(schema["additionalProperties"], defs)
        return f"map<string,{val}>"

    # Empty schema with only properties: {}
    if schema.get("properties") is not None and schema["properties"] == {}:
        return "object"

    return "string"
```

**Add the `_normalize_prefix_items()` helper** right after `canonical_type()`:

```python
def _normalize_prefix_items(schema: dict, defs: dict) -> str:
    """Normalize a fixed-length prefixItems array.

    If all elements have the same type, emit array<T>.
    Otherwise, emit tuple<T1,T2,...>.
    """
    prefix = schema["prefixItems"]
    element_types = [canonical_type(item, defs) for item in prefix]

    if not element_types:
        return "array<ref:Unknown>"

    # If all elements are the same type, use array<T>
    if len(set(element_types)) == 1:
        return f"array<{element_types[0]}>"

    # Heterogeneous: use tuple notation
    return f"tuple<{','.join(element_types)}>"
```

**Also update `_primitive_type()`** — the `"array"` case should no longer blindly return `array<ref:Unknown>` because the caller now handles arrays before reaching this function. Keep it as a fallback but this path should rarely be hit:

```python
def _primitive_type(t: str) -> str:
    mapping = {
        "string": "string",
        "integer": "integer",
        "number": "float",
        "boolean": "boolean",
        "object": "object",
        "array": "array<ref:Unknown>",
    }
    return mapping.get(t, "string")
```

No changes needed to `_primitive_type()` itself — it stays as-is. The fix is entirely in `canonical_type()` checking structured shapes before falling through to primitives.

### Step 1.2: Fix `classify_variants()` to handle nullable payload variants

**Problem**: The Response enum in `reply.schema.json` has variants like:

```json
{
  "properties": {
    "FocusedOutput": {
      "anyOf": [
        { "$ref": "#/$defs/Output" },
        { "type": "null" }
      ]
    }
  },
  "required": ["FocusedOutput"]
}
```

The current `classify_variants()` function checks for `$ref`, `properties`, and `type` in the payload, but **does not check for `anyOf`**. Payloads like `{"anyOf": [{"$ref": ...}, {"type": "null"}]}` fall through to the fallback which produces an empty struct variant.

**Where to fix**: In `classify_variants()`, lines 92–162 of `tools/normalize_ir.py`.

**Required change**: After the `"$ref" in var_payload` check (line 110) and before the `"properties" in var_payload` check (line 122), add a handler for `anyOf`:

```python
            # Newtype variant (ref): {"VariantName": {"$ref": "#/$defs/Type"}}
            if "$ref" in var_payload:
                inner = resolve_ref(var_payload["$ref"])
                variants.append(
                    {
                        "name": var_name,
                        "kind": "newtype",
                        "inner_type": f"ref:{inner}",
                    }
                )
                continue

            # NEW: Nullable ref or complex anyOf payload
            if "anyOf" in var_payload:
                inner = canonical_type(var_payload, defs)
                variants.append(
                    {
                        "name": var_name,
                        "kind": "newtype",
                        "inner_type": inner,
                    }
                )
                continue

            # Struct variant (inline fields)...
```

This handles all four broken Response variants:
- `FocusedOutput`: `anyOf[Output, null]` → `option<ref:Output>` → newtype
- `FocusedWindow`: `anyOf[Window, null]` → `option<ref:Window>` → newtype
- `PickedWindow`: `anyOf[Window, null]` → `option<ref:Window>` → newtype
- `PickedColor`: `anyOf[PickedColor, null]` → `option<ref:PickedColor>` → newtype

**Also handle typed arrays and maps in variant payloads**: The `Outputs` variant has payload `{"type": "object", "additionalProperties": {"$ref": "#/$defs/Output"}}`. The current code falls through to the `"type" in var_payload` branch, which calls `canonical_type()`, which (before our fix) returned `"object"`, causing it to be classified as an empty struct.

After our Step 1.1 fix to `canonical_type()`, this variant payload will now correctly produce `"map<string,ref:Output>"`. The existing code at lines 133–152 already handles this:

```python
            if "type" in var_payload or "$ref" in var_payload:
                inner = canonical_type(var_payload, defs)
                if inner == "object":
                    # ... empty struct
                else:
                    # ... newtype with inner_type = inner
```

With the fixed `canonical_type()`, `Outputs` will now get `inner = "map<string,ref:Output>"` instead of `"object"`, and will correctly become a newtype variant.

Similarly, `Windows`, `Workspaces`, and `Layers` have payloads like `{"type": "array", "items": {"$ref": "#/$defs/Window"}}`. With the fix, `canonical_type()` will now return `"array<ref:Window>"` instead of `"array<ref:Unknown>"`.

### Step 1.3: Update `ir_type_to_python()` in `tools/generate_types.py`

**Add tuple support**: The generator needs to handle the new `tuple<T1,T2,...>` IR type.

Add this case to `ir_type_to_python()` after the `map<` handler:

```python
    if ir_type.startswith("tuple<"):
        inner = ir_type[6:-1]
        parts = inner.split(",")
        py_types = [ir_type_to_python(p.strip()) for p in parts]
        return f"tuple[{', '.join(py_types)}]"
```

### Step 1.4: Update `_extract_refs_from_type()` in `tools/generate_types.py`

This function (lines 380–387) only handles `ref:`, `option<ref:`, and `array<ref:` patterns. It needs to also handle:

- `map<string,ref:X>` patterns
- `tuple<...>` patterns containing refs
- `option<array<ref:X>>` patterns
- `option<map<string,ref:X>>` patterns

**Replace** the function with a more robust recursive extractor:

```python
def _extract_refs_from_type(t: str, refs: set[str]) -> None:
    """Recursively extract all ref:X references from an IR type string."""
    if t.startswith("ref:"):
        name = t[4:]
        if name != "Unknown":
            refs.add(name)
    elif t.startswith("option<"):
        _extract_refs_from_type(t[7:-1], refs)
    elif t.startswith("array<"):
        _extract_refs_from_type(t[6:-1], refs)
    elif t.startswith("map<"):
        parts = t[4:-1].split(",", 1)
        if len(parts) > 1:
            _extract_refs_from_type(parts[1].strip(), refs)
    elif t.startswith("tuple<"):
        inner = t[6:-1]
        for part in inner.split(","):
            _extract_refs_from_type(part.strip(), refs)
```

### Step 1.5: Regenerate all types

After making changes to both `normalize_ir.py` and `generate_types.py`:

```bash
python tools/normalize_ir.py
python tools/generate_types.py
```

### Step 1.6: Verify the regenerated output

After regeneration, manually inspect the key files to confirm correctness.

**Check `src/niri_pypc/types/generated/reply.py`**:

| Class | Before (broken) | After (correct) |
|---|---|---|
| `FocusedOutputResponse` | `pass` (empty) | `payload: Output \| None` |
| `FocusedWindowResponse` | `pass` (empty) | `payload: Window \| None` |
| `OutputsResponse` | `pass` (empty) | `payload: dict[str, Output]` |
| `PickedColorResponse` | `pass` (empty) | `payload: PickedColor \| None` |
| `PickedWindowResponse` | `pass` (empty) | `payload: Window \| None` |
| `LayersResponse` | `payload: list[Any]` | `payload: list[LayerSurface]` |
| `WindowsResponse` | `payload: list[Any]` | `payload: list[Window]` |
| `WorkspacesResponse` | `payload: list[Any]` | `payload: list[Workspace]` |

**Check `src/niri_pypc/types/generated/models.py`** for `Output`:

| Field | Before | After |
|---|---|---|
| `modes` | `list[Any]` | `list[Mode]` |
| `physical_size` | `list[Any] \| None` | `list[int] \| None` or `tuple[int, int] \| None` |

**Check `src/niri_pypc/types/generated/action.py`** for `SpawnAction`:

| Field | Before | After |
|---|---|---|
| `command` | `list[Any]` | `list[str]` |

**Check `src/niri_pypc/types/generated/models.py`** for `WindowLayout`:

| Field | Before | After |
|---|---|---|
| `tile_size` | `list[Any]` | Homogeneous `list[int]` or `tuple[int, int]` |
| `window_size` | `list[Any]` | Same |
| `window_offset_in_tile` | `list[Any]` | Same |

**Check for `PickedColor.rgb`**: Should be `list[float]` or `tuple[float, float, float]` — not `list[Any]`.

### Step 1.7: Fix the `reply.py` import list

After regeneration, `reply.py` will need to import additional types from `models.py` that it didn't need before: `Output`, `Window`, `PickedColor`, `LayerSurface`, `Workspace`. The generator should handle this automatically via `_collect_refs_from_variant()` → `_extract_refs_from_type()`. Verify that the import block at the top of the regenerated `reply.py` includes all needed types.

If the generator's import resolution misses any types, debug `_extract_refs_from_type()` and `_collect_refs_from_variant()`.

### Step 1.8: Ensure `verify_generated.py` passes

If `tools/verify_generated.py` exists and works, run it:

```bash
python tools/verify_generated.py \
  --ir schema/ir/niri-ipc-ir.json \
  --generated-dir src/niri_pypc/types/generated
```

If it does not exist, create it — it should:
1. Run the generator in memory (or to a temp directory).
2. Diff each generated file against the committed version.
3. Exit 0 if no diffs, exit 1 with a diff report otherwise.

A simple implementation:

```python
#!/usr/bin/env python3
"""Verify that committed generated files match what the generator would produce."""

import subprocess
import sys
import tempfile
from pathlib import Path

def main():
    repo_root = Path(__file__).resolve().parent.parent
    generated_dir = repo_root / "src" / "niri_pypc" / "types" / "generated"

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.check_call([
            sys.executable,
            str(repo_root / "tools" / "generate_types.py"),
            "--ir", str(repo_root / "schema" / "ir" / "niri-ipc-ir.json"),
            "--output-dir", tmpdir,
        ])

        import filecmp
        diffs = []
        for f in sorted(Path(tmpdir).iterdir()):
            committed = generated_dir / f.name
            if not committed.exists():
                diffs.append(f"NEW: {f.name}")
            elif f.read_text() != committed.read_text():
                diffs.append(f"DIFF: {f.name}")

        for f in sorted(generated_dir.iterdir()):
            if f.name.startswith("__pycache__"):
                continue
            tmp_f = Path(tmpdir) / f.name
            if not tmp_f.exists():
                diffs.append(f"EXTRA: {f.name}")

    if diffs:
        print("Generated files are out of date:")
        for d in diffs:
            print(f"  {d}")
        sys.exit(1)
    else:
        print("Generated files are up to date.")

if __name__ == "__main__":
    main()
```

### Step 1.9: Add protocol-fidelity regression tests

Create `tests/types/test_generated_shapes.py`. These tests assert that the generated models have the correct field types. They serve as a regression gate — if the generator breaks these shapes again, the tests fail.

```python
"""Regression tests for generated protocol type shapes."""

import typing
from niri_pypc.types.generated.reply import (
    FocusedOutputResponse,
    FocusedWindowResponse,
    LayersResponse,
    OutputsResponse,
    PickedColorResponse,
    PickedWindowResponse,
    VersionResponse,
    WindowsResponse,
    WorkspacesResponse,
)
from niri_pypc.types.generated.models import (
    LayerSurface,
    Mode,
    Output,
    PickedColor,
    Window,
    Workspace,
)
from niri_pypc.types.generated.action import SpawnAction


def _get_field_annotation(model_cls, field_name: str):
    """Get the resolved type annotation for a model field."""
    hints = typing.get_type_hints(model_cls)
    return hints[field_name]


class TestResponsePayloadTypes:
    """Verify that Response variant classes carry the correct payload types."""

    def test_focused_output_response_has_nullable_output_payload(self):
        ann = _get_field_annotation(FocusedOutputResponse, "payload")
        assert ann == Output | None

    def test_focused_window_response_has_nullable_window_payload(self):
        ann = _get_field_annotation(FocusedWindowResponse, "payload")
        assert ann == Window | None

    def test_picked_color_response_has_nullable_picked_color_payload(self):
        ann = _get_field_annotation(PickedColorResponse, "payload")
        assert ann == PickedColor | None

    def test_picked_window_response_has_nullable_window_payload(self):
        ann = _get_field_annotation(PickedWindowResponse, "payload")
        assert ann == Window | None

    def test_outputs_response_has_dict_payload(self):
        ann = _get_field_annotation(OutputsResponse, "payload")
        assert ann == dict[str, Output]

    def test_layers_response_has_typed_list_payload(self):
        ann = _get_field_annotation(LayersResponse, "payload")
        assert ann == list[LayerSurface]

    def test_windows_response_has_typed_list_payload(self):
        ann = _get_field_annotation(WindowsResponse, "payload")
        assert ann == list[Window]

    def test_workspaces_response_has_typed_list_payload(self):
        ann = _get_field_annotation(WorkspacesResponse, "payload")
        assert ann == list[Workspace]

    def test_version_response_has_str_payload(self):
        ann = _get_field_annotation(VersionResponse, "payload")
        assert ann == str


class TestModelFieldTypes:
    """Verify that shared model types have correct field types."""

    def test_output_modes_is_list_of_mode(self):
        ann = _get_field_annotation(Output, "modes")
        assert ann == list[Mode]

    def test_spawn_action_command_is_list_of_str(self):
        ann = _get_field_annotation(SpawnAction, "command")
        assert ann == list[str]
```

### Step 1.10: Add reply round-trip regression test

Create `tests/types/test_reply_roundtrip.py`. This directly tests the bug described in the code review: that `Reply.model_validate(raw).model_dump(mode="json")` preserves payloads.

```python
"""Regression test for reply round-trip fidelity (C4 from code review)."""

from niri_pypc.types.generated.reply import Reply


class TestReplyRoundTrip:
    def test_outputs_response_preserves_payload(self):
        """Outputs payload must survive validate → dump round-trip."""
        raw = {
            "Ok": {
                "Outputs": {
                    "HDMI-A-1": {
                        "name": "HDMI-A-1",
                        "make": "Dell",
                        "model": "X",
                        "serial": "123",
                        "physical_size": None,
                        "logical": None,
                        "current_mode": None,
                        "modes": [],
                        "vrr_supported": False,
                        "vrr_enabled": False,
                    }
                }
            }
        }
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        assert "Ok" in dumped
        inner = dumped["Ok"]
        assert isinstance(inner, dict)
        assert "Outputs" in inner
        outputs = inner["Outputs"]
        assert isinstance(outputs, dict)
        assert "HDMI-A-1" in outputs

    def test_focused_output_null_preserves_null(self):
        raw = {"Ok": {"FocusedOutput": None}}
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        assert dumped == {"Ok": {"FocusedOutput": None}}

    def test_focused_window_with_data_preserves_payload(self):
        raw = {
            "Ok": {
                "FocusedWindow": {
                    "id": 42,
                    "title": "test",
                    "app_id": "test-app",
                }
            }
        }
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        assert dumped["Ok"]["FocusedWindow"]["id"] == 42

    def test_version_round_trip(self):
        raw = {"Ok": {"Version": "25.11"}}
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        assert dumped == {"Ok": {"Version": "25.11"}}

    def test_err_round_trip(self):
        raw = {"Err": "something went wrong"}
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        assert dumped == {"Err": "something went wrong"}

    def test_windows_response_preserves_list(self):
        raw = {
            "Ok": {
                "Windows": [
                    {"id": 1, "title": "win1", "app_id": "app1"},
                    {"id": 2, "title": "win2", "app_id": "app2"},
                ]
            }
        }
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        windows = dumped["Ok"]["Windows"]
        assert len(windows) == 2
        assert windows[0]["id"] == 1

    def test_layers_response_preserves_list(self):
        raw = {
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
        }
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        layers = dumped["Ok"]["Layers"]
        assert len(layers) == 1
        assert layers[0]["namespace"] == "waybar"
```

**Note**: Some of the test fixture payloads above may need adjustment depending on which fields are `required` vs. optional in the generated `Window`, `Output`, etc. models. When you first run these tests after regeneration, check any `ValidationError` messages and add missing required fields to the fixtures.

### Step 1.11: Run the test suite

```bash
PYTHONPATH=src pytest tests/ -q
```

All existing tests plus the new ones should pass. If any existing tests break due to the regenerated types, update the test fixtures — the new types are correct, so tests that relied on broken shapes need updating.

---

## Phase 2: Refactor the error taxonomy

### Step 2.1: Add `EncodeError` to `src/niri_pypc/errors.py`

Add a new error class after `DecodeError`:

```python
class EncodeError(NiriError):
    """Failure during outbound encoding."""
```

### Step 2.2: Centralize payload truncation in `DecodeError`

Currently, `raw_payload` truncation to 1024 chars is done ad-hoc at every call site. Move it into the constructor.

**Change** `DecodeError.__init__()`:

```python
class DecodeError(NiriError):
    """Validation or shape failure during decode."""

    MAX_PAYLOAD_EXCERPT = 1024

    def __init__(
        self,
        message: str,
        *,
        raw_payload: str | None = None,
        **kwargs: Any,
    ) -> None:
        if raw_payload is not None and len(raw_payload) > self.MAX_PAYLOAD_EXCERPT:
            raw_payload = raw_payload[: self.MAX_PAYLOAD_EXCERPT]
        self.raw_payload = raw_payload
        super().__init__(message, **kwargs)
```

Then **remove all `[:1024]` truncations** at call sites in `codec.py` and `framing.py`. After this change, callers just pass `raw_payload=str(data)` and the constructor handles truncation.

### Step 2.3: Add `cause` field to `NiriError`

Add explicit cause tracking so errors carry machine-readable chaining in addition to Python's `__cause__`:

```python
class NiriError(Exception):
    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        socket_path: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.operation = operation
        self.socket_path = socket_path
        self.retryable = retryable
        self.cause = cause
        super().__init__(message)
```

Update all subclass `__init__` signatures to pass through `**kwargs` (they already do for most). Where errors are raised with `from exc`, also pass `cause=exc`.

### Step 2.4: Update `__init__.py` exports

Add `EncodeError` to the public exports in `src/niri_pypc/__init__.py`:

```python
from niri_pypc.errors import (
    ConfigError, DecodeError, EncodeError, InternalError, LifecycleError,
    NiriError, NiriTimeoutError, ProtocolError, RemoteError, TransportError,
)
```

---

## Phase 3: Make codec and reply handling structural

### Step 3.1: Fix `encode_externally_tagged()` to raise `EncodeError`

In `src/niri_pypc/types/codec.py`, change the import and the error:

```python
from niri_pypc.errors import DecodeError, EncodeError, RemoteError
```

Change the unknown variant class error from `DecodeError` to `EncodeError`:

```python
    if wire_name is None:
        raise EncodeError(
            f"Unknown variant class: {cls.__name__}",
            operation="encode_externally_tagged",
        )
```

### Step 3.2: Make `unwrap_reply()` structural instead of name-based

**Current code** dispatches on `type(variant).__name__` string prefix (`"Ok"` / `"Err"`). This is brittle.

**Replace** `unwrap_reply()` entirely:

```python
def unwrap_reply(reply: BaseModel) -> Any:
    """Unwrap a niri Reply envelope.

    Returns the Ok payload value, or raises RemoteError for Err.
    """
    variant = getattr(reply, "variant", None)
    if variant is None:
        raise DecodeError(
            "Reply missing variant field",
            operation="unwrap_reply",
        )

    # Import the concrete types for structural dispatch
    from niri_pypc.types.generated.reply import OkReply, ErrReply

    if isinstance(variant, OkReply):
        return getattr(variant, "payload", variant)
    if isinstance(variant, ErrReply):
        msg = getattr(variant, "payload", str(variant))
        raise RemoteError(
            f"Compositor error: {msg}",
            operation="unwrap_reply",
            remote_message=str(msg),
        )

    raise DecodeError(
        f"Unexpected reply variant: {type(variant).__name__}",
        operation="unwrap_reply",
    )
```

### Step 3.3: Validate dict key type in `decode_externally_tagged()`

Add an explicit check after extracting the variant name:

```python
        variant_name = next(iter(data.keys()))
        if not isinstance(variant_name, str):
            raise DecodeError(
                f"Expected string key in externally-tagged dict, got {type(variant_name).__name__}",
                operation="decode_externally_tagged",
                raw_payload=str(data),
            )
```

Remove the `cast(str, ...)` call that was there before.

---

## Phase 4: Refactor `NiriEventStream`

This is the second major refactoring target. The current event stream has several architectural issues: ambiguous sentinel-based closure, silent error swallowing, unsafe close under full queues, and incorrect `__anext__` semantics.

### Step 4.1: Define explicit queue item types

At the top of `src/niri_pypc/api/event_stream.py`, replace `_StreamClosed` with three explicit types:

```python
from dataclasses import dataclass


@dataclass(slots=True)
class _EventItem:
    """A successfully decoded event."""
    event: BaseModel


@dataclass(slots=True)
class _ErrorItem:
    """A terminal failure (transport or decode)."""
    error: Exception


@dataclass(slots=True)
class _ClosedItem:
    """Stream was closed deliberately."""
    pass


_QueueItem = _EventItem | _ErrorItem | _ClosedItem
```

Update the queue type annotation:

```python
self._queue: asyncio.Queue[_QueueItem] | None = None
```

### Step 4.2: Store terminal cause

Add a `_terminal_cause` field to `NiriEventStream.__init__()`:

```python
def __init__(self, config: NiriConfig) -> None:
    self._config = config
    self._lifecycle = LifecycleManager()
    self._queue: asyncio.Queue[_QueueItem] | None = None
    self._reader_task: asyncio.Task[None] | None = None
    self._connection: UnixConnection | None = None
    self._terminal_cause: Exception | None = None
```

### Step 4.3: Rewrite `_run_reader()`

Replace the entire method. Key changes:
- Decode failures are **terminal** — they enqueue an `_ErrorItem` and stop.
- Transport failures enqueue an `_ErrorItem` with the original `TransportError`.
- `NiriTimeoutError` from `read_frame()` is **not caught** by the `TransportError` handler (it's a separate exception type). The reader should let the socket idle without a timeout — remove `event_read_timeout` from the reader loop. Timeouts belong at the consumer boundary (`next()`).
- Malformed events are **not** silently swallowed.
- The outer `except Exception: pass` is removed.

```python
async def _run_reader(self) -> None:
    """Background task: read frames, decode Events, push to queue."""
    conn = self._connection
    queue = self._queue
    config = self._config
    if conn is None or queue is None:
        return

    try:
        while True:
            try:
                raw = await conn.read_frame(
                    max_size=config.max_frame_size,
                    timeout=None,  # No idle timeout — reader stays open
                )
            except TransportError as exc:
                self._terminal_cause = exc
                self._enqueue_terminal(_ErrorItem(error=exc))
                return
            except NiriTimeoutError as exc:
                # This shouldn't happen with timeout=None, but handle defensively
                self._terminal_cause = exc
                self._enqueue_terminal(_ErrorItem(error=exc))
                return

            try:
                decoded = decode_frame(raw)
                event = Event.model_validate(decoded)
            except Exception as exc:
                # Decode failure is terminal for a pinned protocol library
                from niri_pypc.errors import DecodeError as _DecodeError
                terminal = _DecodeError(
                    f"Failed to decode event: {exc}",
                    operation="event_stream_reader",
                    raw_payload=raw[:1024].decode("utf-8", errors="replace")
                        if isinstance(raw, bytes) else str(raw),
                    cause=exc,
                )
                self._terminal_cause = terminal
                self._enqueue_terminal(_ErrorItem(error=terminal))
                return

            # Enqueue the event with backpressure handling
            item = _EventItem(event=event.variant)
            if config.backpressure_mode == BackpressureMode.DROP_OLDEST:
                try:
                    queue.put_nowait(item)
                except asyncio.QueueFull:
                    import logging
                    logging.getLogger("niri_pypc.event_stream").warning(
                        "Event queue full, dropping oldest event"
                    )
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    queue.put_nowait(item)
            else:  # FAIL_FAST
                try:
                    queue.put_nowait(item)
                except asyncio.QueueFull:
                    from niri_pypc.errors import ProtocolError
                    exc = ProtocolError(
                        "Event queue full (FAIL_FAST mode)",
                        operation="event_stream_reader",
                    )
                    self._terminal_cause = exc
                    self._enqueue_terminal(_ErrorItem(error=exc))
                    return
    finally:
        await self._close_reader_resources()
```

### Step 4.4: Add `_enqueue_terminal()` helper

This safely enqueues a terminal item even when the queue is full:

```python
def _enqueue_terminal(self, item: _ErrorItem | _ClosedItem) -> None:
    """Enqueue a terminal item, displacing a stale event if the queue is full."""
    if self._queue is None:
        return
    try:
        self._queue.put_nowait(item)
    except asyncio.QueueFull:
        # Terminal state outranks stale queued events — displace one
        try:
            self._queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            pass  # Should not happen after get_nowait, but be safe
```

### Step 4.5: Rewrite `_close_from_reader()` → `_close_reader_resources()`

Rename and fix to actually close the connection:

```python
async def _close_reader_resources(self) -> None:
    """Clean up resources when the reader task exits."""
    if self._lifecycle.is_terminal:
        return
    try:
        await self._lifecycle.transition_to(LifecycleState.CLOSING)
    except LifecycleError:
        return  # Already closing/closed from another path
    # Close the actual connection (don't just drop the reference)
    if self._connection is not None and not self._connection.is_closed:
        await self._connection.close()
    self._connection = None
    # Enqueue closed sentinel if no terminal cause was already enqueued
    if self._terminal_cause is None:
        self._enqueue_terminal(_ClosedItem())
    try:
        await self._lifecycle.transition_to(LifecycleState.CLOSED)
    except LifecycleError:
        pass
```

### Step 4.6: Rewrite `next()`

Dispatch on the actual queue item type instead of checking for `_StreamClosed`:

```python
async def next(self, *, timeout: float | None = None) -> BaseModel:
    """Read the next event from the stream.

    Args:
        timeout: Seconds to wait. None uses config.event_read_timeout.

    Returns:
        A decoded event variant model instance.

    Raises:
        NiriTimeoutError: If timeout expires with no event.
        TransportError: If the connection was lost.
        DecodeError: If a malformed event terminated the stream.
        LifecycleError: If the stream was closed deliberately.
    """
    if self._lifecycle.is_terminal:
        if self._terminal_cause is not None:
            raise self._terminal_cause
        raise LifecycleError(
            "Event stream is closed",
            operation="next",
            state=self._lifecycle.state.value,
        )
    if self._queue is None:
        raise InternalError(
            "Event stream not connected",
            operation="next",
        )

    read_timeout = timeout if timeout is not None else self._config.event_read_timeout
    try:
        item = await asyncio.wait_for(self._queue.get(), timeout=read_timeout)
    except TimeoutError:
        from niri_pypc.errors import NiriTimeoutError
        raise NiriTimeoutError(
            "No event received within timeout",
            operation="next",
            retryable=True,
        ) from None

    if isinstance(item, _EventItem):
        return item.event
    if isinstance(item, _ErrorItem):
        raise item.error
    if isinstance(item, _ClosedItem):
        raise LifecycleError(
            "Event stream has been closed",
            operation="next",
            state=self._lifecycle.state.value,
        )

    raise InternalError(
        f"Unexpected queue item type: {type(item).__name__}",
        operation="next",
    )
```

### Step 4.7: Fix `__anext__()` to raise `StopAsyncIteration`

```python
async def __anext__(self) -> BaseModel:
    try:
        return await self.next()
    except LifecycleError:
        raise StopAsyncIteration from None
```

The `_async_iterator()` method used by `__aiter__()` should also be updated:

```python
def __aiter__(self) -> AsyncIterator[BaseModel]:
    return self._async_iterator()

async def _async_iterator(self) -> AsyncIterator[BaseModel]:
    while True:
        try:
            yield await self.next()
        except (LifecycleError, StopAsyncIteration):
            break
```

### Step 4.8: Rewrite `close()`

Make close safe against full queues:

```python
async def close(self) -> None:
    """Close the event stream. Idempotent."""
    if self._lifecycle.is_terminal:
        return
    try:
        await self._lifecycle.transition_to(LifecycleState.CLOSING)
    except LifecycleError:
        return

    # Cancel the reader task
    if self._reader_task is not None and not self._reader_task.done():
        self._reader_task.cancel()
        try:
            await self._reader_task
        except (asyncio.CancelledError, Exception):
            pass

    # Close the connection
    if self._connection is not None and not self._connection.is_closed:
        await self._connection.close()
    self._connection = None

    # Signal closure to consumers (safe under full queue)
    self._enqueue_terminal(_ClosedItem())

    await self._lifecycle.transition_to(LifecycleState.CLOSED)
```

### Step 4.9: Update imports

At the top of `event_stream.py`, update the imports:

```python
import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from niri_pypc.config import BackpressureMode, NiriConfig
from niri_pypc.errors import (
    InternalError,
    LifecycleError,
    NiriTimeoutError,
    TransportError,
)
from niri_pypc.runtime.lifecycle import LifecycleManager, LifecycleState
from niri_pypc.transport.connection import UnixConnection
from niri_pypc.transport.framing import decode_frame, encode_frame
from niri_pypc.types.generated.event import Event
```

### Step 4.10: Add event stream regression tests

Create or update `tests/api/test_event_stream.py` with new tests:

```python
class TestEventStreamEdgeCases:
    async def test_close_with_full_queue_does_not_raise(self, mock_event_server):
        """close() must not raise QueueFull."""
        config = NiriConfig(
            socket_path=mock_event_server["path"],
            event_queue_capacity=1,  # Very small queue
        )
        stream = await NiriEventStream.connect(config)
        # Let the queue fill up
        await asyncio.sleep(0.1)
        # close() should not raise
        await stream.close()

    async def test_async_for_stops_on_close(self, mock_event_server):
        """async for should end cleanly when stream is closed."""
        config = NiriConfig(socket_path=mock_event_server["path"])
        stream = await NiriEventStream.connect(config)
        events = []
        async def collect():
            async for event in stream:
                events.append(event)
        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)
        await stream.close()
        await task  # Should complete without raising
```

---

## Phase 5: Simplify `NiriClient`

### Step 5.1: Remove `LifecycleManager` from `NiriClient`

Replace the lifecycle manager with a simple boolean flag. The client doesn't own a persistent connection — it opens a fresh socket per request. A full state machine is unnecessary.

**Rewrite `src/niri_pypc/api/client.py`**:

```python
"""Command client for niri IPC."""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from niri_pypc.config import NiriConfig
from niri_pypc.errors import LifecycleError
from niri_pypc.transport.connection import UnixConnection
from niri_pypc.transport.framing import decode_frame, encode_frame
from niri_pypc.types.codec import unwrap_reply
from niri_pypc.types.generated.reply import Reply


class NiriClient:
    """Command client for niri IPC.

    Uses one-connection-per-request model: each request() call opens a new
    Unix socket connection, sends the request, reads the response, and closes.
    """

    def __init__(self, config: NiriConfig) -> None:
        self._config = config
        self._closed = False

    @classmethod
    def connect(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriClient:
        """Create a client. Validates config but does not open a socket yet."""
        if config is None:
            config = NiriConfig()
        config.resolve_socket_path()
        return cls(config)

    async def request(self, req: BaseModel, *, timeout: float | None = None) -> Any:
        """Send a request and return the decoded response payload.

        Args:
            req: A request variant model instance (e.g., VersionRequest()).
            timeout: Override request timeout. If None, use config.request_timeout.

        Returns:
            The decoded Ok payload (Response variant model).

        Raises:
            TransportError: Socket I/O failure.
            NiriTimeoutError: Request exceeded timeout.
            DecodeError: Response could not be decoded.
            RemoteError: Compositor returned an Err response.
            LifecycleError: Client has been closed.
        """
        if self._closed:
            raise LifecycleError(
                "Client is closed",
                operation="request",
                state="closed",
            )

        socket_path = self._config.resolve_socket_path()
        read_timeout = timeout if timeout is not None else self._config.request_timeout

        conn = await UnixConnection.connect(
            socket_path,
            timeout=self._config.connect_timeout,
        )
        try:
            from niri_pypc.types.generated.request import Request as RequestModel

            request_root = RequestModel(variant=cast(Any, req))
            payload = request_root.model_dump(mode="json")
            frame = encode_frame(payload)
            await conn.write_frame(frame)

            raw = await conn.read_frame(
                max_size=self._config.max_frame_size,
                timeout=read_timeout,
            )
            decoded = decode_frame(raw)
            reply = Reply.model_validate(decoded)
            return unwrap_reply(reply)
        finally:
            await conn.close()

    async def close(self) -> None:
        """Close the client. Idempotent."""
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def __aenter__(self) -> NiriClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
```

### Step 5.2: Make `UnixConnection` an async context manager

Add these methods to `src/niri_pypc/transport/connection.py`:

```python
    async def __aenter__(self) -> UnixConnection:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
```

### Step 5.3: Simplify `UnixConnection.close()`

Remove the unnecessary `hasattr()` checks:

```python
    async def close(self) -> None:
        """Close the connection. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except OSError:
            pass
```

### Step 5.4: Update tests for the simplified client

Any test that checks `self._lifecycle` state on the client should be updated to check `self._closed` or `client.is_closed` instead. The `test_lifecycle.py` tests for `LifecycleManager` itself remain unchanged — they're still used by `NiriEventStream`.

---

## Phase 6: Thin out `NiriConnectionBundle`

### Step 6.1: Remove lifecycle from the bundle

Replace the entire `src/niri_pypc/api/bundle.py`:

```python
"""Convenience wrapper for command client and event stream."""

from __future__ import annotations

from typing import Any

from niri_pypc.api.client import NiriClient
from niri_pypc.api.event_stream import NiriEventStream
from niri_pypc.config import NiriConfig


class NiriConnectionBundle:
    """Convenience wrapper holding both a command client and event stream.

    Lifetime semantics:
    - Closing the bundle closes both members.
    - Members have independent error isolation: one failing does not
      force-close the other.
    - Access members via .client and .events properties.
    """

    def __init__(self, client: NiriClient, events: NiriEventStream) -> None:
        self._client = client
        self._events = events
        self._closed = False

    @classmethod
    async def open(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriConnectionBundle:
        """Open both command and event connections.

        If event stream connection fails after client succeeds,
        the client is closed before raising.
        """
        if config is None:
            config = NiriConfig()

        client = NiriClient.connect(config)
        try:
            events = await NiriEventStream.connect(config)
        except Exception:
            await client.close()
            raise

        return cls(client, events)

    @property
    def client(self) -> NiriClient:
        return self._client

    @property
    def events(self) -> NiriEventStream:
        return self._events

    async def close(self) -> None:
        """Close both connections. Idempotent.

        Closes both members, preserving best-effort independent shutdown.
        """
        if self._closed:
            return
        self._closed = True

        first_exc = None
        try:
            await self._client.close()
        except Exception as exc:
            first_exc = exc
        try:
            await self._events.close()
        except Exception as exc:
            if first_exc is None:
                first_exc = exc

        if first_exc is not None:
            raise first_exc

    async def __aenter__(self) -> NiriConnectionBundle:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
```

The key changes:
- No `LifecycleManager` import
- No `self._lifecycle._state = LifecycleState.READY` hack
- Simple `self._closed` flag for idempotency
- Otherwise identical behavior

### Step 6.2: Update bundle tests

Tests that inspect `bundle._lifecycle` should be updated to check `bundle._closed` instead. The bundle's close behavior and member independence tests should still pass.

---

## Phase 7: Remove dead configuration

### Step 7.1: Remove `strict_version_check` from `NiriConfig`

In `src/niri_pypc/config.py`, delete this line from the dataclass:

```python
    strict_version_check: bool = True    # DELETE THIS LINE
```

### Step 7.2: Update any tests that reference `strict_version_check`

Search tests for `strict_version_check` and remove those assertions or fixture values.

### Step 7.3: Move the lazy `ConfigError` import to module level

In `config.py`, the `resolve_socket_path()` method has a lazy import:

```python
    def resolve_socket_path(self) -> Path:
        ...
        from niri_pypc.errors import ConfigError   # ← lazy
```

Move this to the top of the file:

```python
from niri_pypc.errors import ConfigError
```

Then use it directly in the method. This is safe — there is no circular import between `config.py` and `errors.py`.

---

## Phase 8: Wrap frame-encoding errors properly

### Step 8.1: Handle serialization errors in `encode_frame()`

In `src/niri_pypc/transport/framing.py`:

```python
from niri_pypc.errors import DecodeError, EncodeError


def encode_frame(data: Any) -> bytes:
    """Serialize data to a newline-terminated JSON frame."""
    try:
        return json.dumps(data, separators=(",", ":")).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise EncodeError(
            f"Failed to encode frame: {exc}",
            operation="encode_frame",
        ) from exc
```

---

## Phase 9: Repository hygiene

### Step 9.1: Update `.gitignore`

The existing `.gitignore` already has `tools/schema_exporter/target/` and `__pycache__/`. Verify these entries are present. If Rust build artifacts are tracked, remove them:

```bash
# Check if target/ is tracked
git ls-files tools/schema_exporter/target/
# If any files are listed:
git rm -r --cached tools/schema_exporter/target/
```

### Step 9.2: Clean any committed `__pycache__` or `.pyc` files

```bash
git ls-files '*.pyc' '*__pycache__*'
# If any files are listed:
git rm -r --cached '**/__pycache__/' '**/*.pyc'
```

### Step 9.3: Add `.scratch/` to `.gitignore` if not present

If there's a `.scratch/` directory with review documents, ensure it's in `.gitignore`.

---

## Phase 10: Final verification

### Step 10.1: Run the full pipeline end-to-end

```bash
# 1. Regenerate IR from schema
python tools/normalize_ir.py

# 2. Regenerate types from IR
python tools/generate_types.py

# 3. Verify generated files match
python tools/verify_generated.py --ir schema/ir/niri-ipc-ir.json \
  --generated-dir src/niri_pypc/types/generated

# 4. Run full test suite
PYTHONPATH=src pytest tests/ -q --tb=short
```

### Step 10.2: Check the specific acceptance criteria

Run these quick checks in a Python shell:

```python
# 1. Reply round-trip (the original repro from the code review)
from niri_pypc.types.generated.reply import Reply

raw = {"Ok": {"Outputs": {"HDMI-A-1": {"name": "HDMI-A-1", "make": "Dell",
       "model": "X", "serial": "123", "physical_size": None, "logical": None,
       "current_mode": None, "modes": [], "vrr_supported": False,
       "vrr_enabled": False}}}}
reply = Reply.model_validate(raw)
dumped = reply.model_dump(mode="json")
assert "Outputs" in dumped["Ok"]
assert "HDMI-A-1" in dumped["Ok"]["Outputs"]
print("✓ Outputs round-trip preserved")

# 2. Nullable payload
raw2 = {"Ok": {"FocusedOutput": None}}
reply2 = Reply.model_validate(raw2)
dumped2 = reply2.model_dump(mode="json")
assert dumped2 == {"Ok": {"FocusedOutput": None}}
print("✓ Nullable FocusedOutput preserved")

# 3. Version round-trip
raw3 = {"Ok": {"Version": "25.11"}}
reply3 = Reply.model_validate(raw3)
assert reply3.model_dump(mode="json") == raw3
print("✓ Version round-trip preserved")
```

### Step 10.3: Final acceptance checklist

- [ ] `normalize_ir.py` preserves typed arrays, maps, nullable refs, and prefixItems
- [ ] `generate_types.py` emits correct Python types for all IR type strings
- [ ] No high-value protocol fields degrade to `Any` without necessity
- [ ] `FocusedOutputResponse`, `FocusedWindowResponse`, `PickedColorResponse`, `PickedWindowResponse` carry nullable payload fields
- [ ] `OutputsResponse` carries `dict[str, Output]`
- [ ] `LayersResponse`, `WindowsResponse`, `WorkspacesResponse` carry typed lists
- [ ] `SpawnAction.command` is `list[str]`
- [ ] `Output.modes` is `list[Mode]`
- [ ] Reply round-trip test passes (no data loss)
- [ ] `verify_generated` exits 0
- [ ] Event stream `close()` never raises `QueueFull`
- [ ] Transport errors surface as `TransportError` from `next()`
- [ ] Malformed events surface as `DecodeError` (not silently swallowed)
- [ ] `async for` ends cleanly on stream closure via `StopAsyncIteration`
- [ ] `NiriClient` has no `LifecycleManager`
- [ ] `NiriConnectionBundle` has no `LifecycleManager`
- [ ] `encode_externally_tagged` raises `EncodeError`, not `DecodeError`
- [ ] `unwrap_reply` dispatches on `isinstance`, not class name prefix
- [ ] `DecodeError` centralizes truncation in its constructor
- [ ] `strict_version_check` is removed from `NiriConfig`
- [ ] No `__pycache__` or Rust `target/` directories are tracked in git
- [ ] All tests pass

---

## Summary of files changed

### Modified files

| File | Changes |
|---|---|
| `tools/normalize_ir.py` | Rewrite `canonical_type()`, add `_normalize_prefix_items()`, fix `classify_variants()` |
| `tools/generate_types.py` | Add `tuple<>` support in `ir_type_to_python()`, fix `_extract_refs_from_type()` |
| `src/niri_pypc/errors.py` | Add `EncodeError`, add `cause` field, centralize truncation |
| `src/niri_pypc/config.py` | Remove `strict_version_check`, top-level `ConfigError` import |
| `src/niri_pypc/types/codec.py` | Use `EncodeError`, structural `unwrap_reply()`, validate dict key |
| `src/niri_pypc/api/event_stream.py` | Explicit queue item types, terminal cause tracking, queue-safe close, correct `__anext__`, no silent error swallowing |
| `src/niri_pypc/api/client.py` | Remove `LifecycleManager`, use `_closed: bool` |
| `src/niri_pypc/api/bundle.py` | Remove `LifecycleManager`, thin coordinator |
| `src/niri_pypc/transport/connection.py` | Add async context manager, simplify `close()` |
| `src/niri_pypc/transport/framing.py` | Wrap encode errors as `EncodeError` |
| `src/niri_pypc/__init__.py` | Export `EncodeError` |
| `.gitignore` | Verify coverage |

### New files

| File | Purpose |
|---|---|
| `tests/types/test_generated_shapes.py` | Type annotation regression tests |
| `tests/types/test_reply_roundtrip.py` | Reply round-trip fidelity tests |
| `tools/verify_generated.py` | Generated file drift check (if not already present) |

### Regenerated files (do not edit by hand)

| File | |
|---|---|
| `schema/ir/niri-ipc-ir.json` | Regenerated from fixed normalizer |
| `src/niri_pypc/types/generated/_metadata.py` | Regenerated |
| `src/niri_pypc/types/generated/models.py` | Regenerated — fields now correctly typed |
| `src/niri_pypc/types/generated/action.py` | Regenerated — `SpawnAction.command` now `list[str]` |
| `src/niri_pypc/types/generated/event.py` | Regenerated |
| `src/niri_pypc/types/generated/request.py` | Regenerated |
| `src/niri_pypc/types/generated/reply.py` | Regenerated — Response variants now carry payloads |
| `src/niri_pypc/types/generated/__init__.py` | Regenerated |

---

## Execution order

The phases should be executed in order. Each phase builds on the previous one.

1. **Phase 1** (Steps 1.1–1.11): Fix the generation pipeline. This is the foundation.
2. **Phase 2** (Steps 2.1–2.4): Error taxonomy cleanup. Quick and needed by Phase 3.
3. **Phase 3** (Steps 3.1–3.3): Codec and reply handling.
4. **Phase 4** (Steps 4.1–4.10): Event stream refactor. The biggest runtime change.
5. **Phase 5** (Steps 5.1–5.4): Simplify client.
6. **Phase 6** (Steps 6.1–6.2): Thin bundle.
7. **Phase 7** (Steps 7.1–7.3): Remove dead config.
8. **Phase 8** (Step 8.1): Frame encoding errors.
9. **Phase 9** (Steps 9.1–9.3): Repo hygiene.
10. **Phase 10** (Steps 10.1–10.3): Final verification.

Run the test suite after every phase. Fix any regressions before moving to the next phase.
