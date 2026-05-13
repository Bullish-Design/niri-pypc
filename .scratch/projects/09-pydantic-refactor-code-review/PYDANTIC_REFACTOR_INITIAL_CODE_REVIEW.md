# Pydantic Refactor v2 Code Review

**Date:** 2026-05-12  
**Ref:** Based on `.scratch/projects/08-pydantic-refactor-v2/PYDANTIC_REFACTOR_PLAN.md`  
**Reviewer:** opencode agent

---

## Executive Summary

The Pydantic v2 refactor has been **largely successful**. The core architecture has been implemented correctly, with protocol types now properly using explicit variant metadata (`__niri_wire_name__`, `__niri_variant_kind__`) instead of field-shape heuristics. Most acceptance criteria from the refactor plan have been met.

**Overall Assessment:** The refactor is complete and functional. There are minor issues that should be addressed, but the core architectural goals have been achieved.

---

## Phase-by-Phase Review

### Phase 1: Protocol Base Layer

**Status:** ✅ Implemented correctly

The base types in `src/niri_pypc/types/base.py` are well-structured:
- `ProtocolModel` with proper `frozen=True`, `extra="forbid"`, `populate_by_name=True`
- `ProtocolVariant` with class-level metadata attributes
- `ExternallyTaggedEnum` using `RootModel` with proper serialization
- `UnknownEvent` sentinel for forward compatibility

**Issue:** `strict=False` in base.py line 18 - the plan specified `strict=True` but implementation has `strict=False`. This is a minor deviation.

---

### Phase 2: Codec Implementation

**Status:** ✅ Implemented correctly

The codec properly uses metadata-driven encoding/decoding:
- No field-shape heuristics remain
- Zero-field structs encode as `{Tag: {}}`
- Unit variants encode as strings
- Newtypes encode as `{Tag: payload}`

The `decode_externally_tagged()` and `encode_externally_tagged()` functions correctly use `__niri_variant_kind__` for all decisions.

---

### Phase 3: Generated Types

**Status:** ✅ Implemented correctly with minor issues

All generated files follow the new architecture:
- Variants properly have `__niri_wire_name__` and `__niri_variant_kind__`
- `Request`, `Reply`, `Response`, `Event`, `Action` are `RootModel` wrappers
- Helper enums (`Transform`, `Layer`, `ColumnDisplay`) are `StrEnum`
- `Reply.unwrap()` method is present
- No `UnknownReply` exists

**Issues Found:**
1. **Unused imports:** Some generated files import `ProtocolModel` but don't use it (F401)
2. **Type alias style:** Generated code uses `TypeAlias = ...` instead of modern `type ... =` syntax (UP040 lint rule)

---

### Phase 4: Transport Edges

**Status:** ✅ Implemented correctly

`NiriClient.request()` correctly:
- Accepts request variants directly
- Internally wraps with `Request(root=req)`
- Serializes with `model_dump_json()`
- Parses reply with `Reply.model_validate_json(raw)`
- Returns `reply.unwrap()` directly

`framing.py` has been correctly reduced to minimal utility with no JSON handling.

---

### Phase 5: Event Stream Bootstrap

**Status:** ✅ Implemented correctly

Event stream bootstrap is explicit:
- `_bootstrap()` sends `EventStreamRequest`
- Validates reply as `HandledResponse`
- Only then allows stream to become ready
- First yielded item is always an event, never a reply

---

### Phase 6: Tests and Fixtures

**Status:** ✅ Tests updated, some minor issues remain

Tests properly use `.root` instead of `.variant`:
- `test_generated_contract.py` - good semantic contract tests
- `test_client.py` - properly tests new API
- `test_event_stream.py` - correctly sends bootstrap reply

**Issue:** Some test files still reference `.variant_name` on `UnknownEvent` (e.g., `test_event_stream.py:149`, `test_unknown_variants.py`) - this is correct usage for the new architecture, not the old pattern.

---

## Verification Results

### Tests
```
pytest -q: ✅ All tests pass (133 passed, 2 skipped)
```

### Linting
```
ruff check .: ⚠️ 15 issues found
  - 13 UP040 (type alias style)
  - 2 F401 (unused imports)
```

### Formatting
```
ruff format --check .: ✅ All files pass (generated files excluded via pyproject.toml)
```

### Type Checking
```
ty check .: ⚠️ 7 type errors (all type narrowing issues)
```

---

## Issues Summary

### High Priority
None - the core functionality works correctly.

### Medium Priority
1. **Type checking issues** in `base.py` and `codec.py` - runtime works but type checker complains about attribute access on generic `ProtocolVariant` types
2. **Type alias style** - Generated code should use `type` keyword instead of `TypeAlias`

### Low Priority
1. `strict=False` in base.py instead of `strict=True` per plan
2. Minor unused imports in generated code

---

## Recommendations

### 1. Fix Type Narrowing (Medium)
The type errors are due to Pydantic generic type narrowing. Consider:
- Adding `# type: ignore` comments for known-safe code paths
- Or restructuring codec to use isinstance checks with explicit type narrowing

### 2. Update Type Alias Style (Low)
The generator should use Python 3.10+ `type` keyword syntax:
```python
# Current
ActionValue: TypeAlias = ...

# Preferred
type ActionValue = ...
```

### 4. Fix Strict Mode (Low)
Update `base.py` to use `strict=True` as specified in the plan.

---

## Verification Against Plan Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| Base layer exists and is clean | ✅ |
| No generated code depends on it yet | ✅ (dependencies exist, which is correct) |
| Tests for base behavior pass | ✅ |
| Codec has zero model_fields heuristics | ✅ |
| Zero-field structs encode as `{Tag: {}}` | ✅ |
| No reply-unwrapping helper in codec | ✅ |
| ToggleOverviewAction carries `__niri_variant_kind__ = "struct"` | ✅ |
| VersionRequest carries `__niri_variant_kind__ = "unit"` | ✅ |
| ErrReply carries `__niri_variant_kind__ = "newtype"` | ✅ |
| Action, Request, Reply, Response, Event are RootModel | ✅ |
| All-unit helper enums are StrEnum | ✅ |
| UnknownReply no longer exists | ✅ |
| Client path never calls json.loads/dumps | ✅ |
| Request returns response variant objects directly | ✅ |
| Stream never misclassifies bootstrap reply as event | ✅ |
| READY means stream is bootstrapped | ✅ |
| No .variant in source code | ✅ |

---

## Conclusion

The Pydantic v2 refactor has been **successfully implemented**. The core architectural changes are correct:
- Protocol truth is represented explicitly in generated models
- Externally tagged enums use `RootModel`
- Variant kind is preserved as metadata
- Transport edges use Pydantic JSON APIs directly
- Event stream bootstrap is explicit and validated

The minor issues identified (formatting, type aliases, type checking) do not affect runtime functionality and can be addressed in a follow-up cleanup pass.