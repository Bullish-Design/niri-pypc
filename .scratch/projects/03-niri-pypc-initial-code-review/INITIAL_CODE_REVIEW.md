# INITIAL CODE REVIEW — niri-pypc

**Reviewer:** Automated deep analysis  
**Date:** 2026-05-11  
**Codebase state:** All 41 tests passing; lint shows 7 fixable errors; type check shows 32 diagnostics.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture & Spec Adherence](#2-architecture--spec-adherence)
3. [Critical Issues](#3-critical-issues)
4. [Significant Issues](#4-significant-issues)
5. [Moderate Issues](#5-moderate-issues)
6. [Minor Issues & Style](#6-minor-issues--style)
7. [Generated Code Quality](#7-generated-code-quality)
8. [Tooling & Pipeline](#8-tooling--pipeline)
9. [Test Suite Analysis](#9-test-suite-analysis)
10. [Type Safety Gaps](#10-type-safety-gaps)
11. [Concurrency & Safety Concerns](#11-concurrency--safety-concerns)
12. [Positive Findings](#12-positive-findings)
13. [Recommendations Summary](#13-recommendations-summary)

---

## 1. Executive Summary

The library implements a pinned IPC protocol client for the Niri Wayland compositor. It follows a clean architecture separating generated protocol types from hand-written runtime logic. The pipeline (Rust schema export → IR normalization → Pydantic type generation → runtime) is well-designed and deterministic. Tests pass and the codebase is functionally coherent.

However, there are **32 type-checking diagnostics**, **7 lint errors** (all fixable), several design concerns around type narrowing, and a number of areas where the code does not fully exploit Pydantic v2's capabilities or the spec's own type system. The `ty check` failure rate is high enough to indicate real type-safety gaps, not just false positives.

---

## 2. Architecture & Spec Adherence

**GOOD:**
- Package structure matches the spec (Section 2, Module Map) exactly.
- Dependency DAG is honored: `api → transport, runtime, types, errors`; `transport → runtime, errors`; `runtime → errors`; `types → (none)`. No cycles.
- Generated code lives in `src/niri_pypc/types/generated/` and is never hand-edited.
- Schema pinning at `niri-ipc 25.11` is consistent across `schema/upstream-pin.toml`, `tools/schema_exporter/Cargo.toml`, and `_metadata.py`.
- The externally-tagged enum pattern with `model_validator(mode="before")` and `model_serializer` is correctly implemented.
- Unknown sentinel support (for inbound `Reply` and `Event` only) matches the spec.
- Lifecycle state machine transitions match the spec diagram.
- One-connection-per-request model for `NiriClient` matches the spec.

**CONCERN:**
- The spec (Section 13) mentions `helpers.py` in the module map, but this file does not exist. Minor documentation drift.

---

## 3. Critical Issues

### CRIT-1: `unwrap_reply` uses class name prefix matching instead of type dispatch

**File:** `src/niri_pypc/types/codec.py:141-151`

```python
cls_name = type(variant).__name__
if cls_name.startswith("Ok"):
    return getattr(variant, "payload", variant)
if cls_name.startswith("Err"):
```

This relies on naming convention (`OkReply`, `ErrReply`) rather than explicit type checks or a dispatch map. This is fragile — if a generated variant class were renamed, or if a user constructed a model with a matching prefix name, the unwrap logic would silently misbehave. The spec defines exactly two variants (`Ok` and `Err` in the Reply enum); the code should use the generated `_REPLY_VARIANTS` dict or explicit `isinstance` checks against `OkReply` and `ErrReply`.

### CRIT-2: `NiriEventStream._run_reader` swallows all exceptions silently

**File:** `src/niri_pypc/api/event_stream.py:100-105`

```python
try:
    decoded = decode_frame(raw)
    event = Event.model_validate(decoded)
except Exception:
    # Malformed event — skip it
    continue
```

A bare `except Exception: continue` silently discards decode failures, including potentially serious errors like `KeyboardInterrupt` subclasses (though unlikely in practice) or memory errors. At minimum, this should log the error. More importantly, a `DecodeError` from a genuinely corrupt protocol stream should arguably signal to the caller that the connection is unhealthy, not be silently skipped.

### CRIT-3: `NiriEventStream.close()` races with `_run_reader` lifecycle transitions

**File:** `src/niri_pypc/api/event_stream.py:128-136` vs `199-215`

Both `_close_from_reader()` (line 128) and `close()` (line 199) transition the lifecycle to `CLOSING` and then `CLOSED`. There is no lock protecting these transitions from each other. If `close()` is called while `_run_reader` is also calling `_close_from_reader()`, the double `transition_to(CLOSING)` would succeed (the transition map allows CLOSING→CLOSING via the "any → CLOSED" rule at line 60-62, but the explicit CLOSING→CLOSING path is not in `_VALID_TRANSITIONS` — it falls through to the `target == LifecycleState.CLOSED` special case, which would fail because it checks `self._state != LifecycleState.CLOSED` and then falls through to the `allowed` check which would be empty). Actually, tracing the code more carefully:

- `_VALID_TRANSITIONS[CLOSING] = {CLOSED}`
- The special case `target == CLOSED and self._state != CLOSED` catches the CLOSING→CLOSED case.
- But if two coroutines both call `transition_to(CLOSING)` concurrently, the first succeeds (CONNECTING/READY→CLOSING), the second would try CLOSING→CLOSING which is NOT in the valid transitions AND doesn't match the CLOSED special case, so it would raise `LifecycleError`.

However, since `_run_reader` checks `is_terminal` first (line 130), and `close()` also checks `is_terminal` first (line 201), there is a window where both pass the check before either sets the state. The asyncio.Lock inside `transition_to` serializes the calls, but the state after the first transition may cause the second to fail.

### CRIT-4: `NiriClient.request()` does not handle cancellation cleanly

**File:** `src/niri_pypc/api/client.py:85-102`

If an `asyncio.CancelledError` is raised during `write_frame`, `read_frame`, or `model_validate`, the `finally` block closes the connection, but the `CancelledError` propagates. This is correct behavior, but the spec (Section 20) says "Cancellation during await read exits predictably and preserves lifecycle invariants." The client's lifecycle is not affected (it uses a boolean `_closed` check, not the lifecycle manager for per-request state), but if a `CancelledError` occurs after `write_frame` but before `read_frame` completes, the connection is left in a state where the server may still be processing the request. This is inherent to the one-connection-per-request model and not a bug per se, but worth documenting.

---

## 4. Significant Issues

### SIG-1: `ty check` reveals 32 type-safety diagnostics

The type checker (`ty check`) reports 32 diagnostics. The most impactful categories:

**a) `BaseModel` attribute access is unknown to the type checker:**

Throughout the codebase, Pydantic `BaseModel` instances are accessed via `.variant`, `.payload`, `.id`, `.focused`, etc., but the type checker cannot resolve these because the union types are too broad. For example:

- `tests/integration/test_event_flow.py:44` — `event.id` and `event.focused` flagged on `BaseModel`
- `tests/integration/test_independence.py:45` — `event.id` flagged on `BaseModel`
- `tests/api/test_client.py:56` — `result.variant.payload` flagged

This is a fundamental tension: the dynamically-typed nature of discriminated unions in Pydantic v2 means the type checker sees `BaseModel` at runtime. The codebase could benefit from explicit type narrowing (e.g., `assert isinstance(event.variant, WorkspaceActivatedEvent)`) or from using Pydantic's `Discriminator`/`TaggedUnion` features more aggressively.

**b) `generate_types.py` uses `Any` liberally:**

The generator uses `Any` in:
- `ir_type_to_python("object")` returns `"dict[str, Any]"` (line 74)
- Several IR schema types map to `Any` (line 91)
- Generated models like `Output` and `Window` have `list[Any]` and `dict[str, Any]` fields

This is somewhat expected for a protocol bridge where upstream types may be opaque, but it undermines the "high-confidence typing" goal stated in the concept (Section 4, point 4).

### SIG-2: `encode_externally_tagged` raises `DecodeError` instead of a dedicated encode error

**File:** `src/niri_pypc/types/codec.py:99-103`

```python
if wire_name is None:
    raise DecodeError(
        f"Unknown variant class: {cls.__name__}",
        operation="encode_externally_tagged",
    )
```

Encoding errors should not be `DecodeError` (which semantically means "failed to decode"). This should be a new error type (e.g., part of a future `EncodeError`) or at minimum `InternalError`. The spec (Section 8) says `EncodeError (subclass of NiriError)` should be raised for unknown outbound variants.

### SIG-3: `_run_reader` does not log dropped events under DROP_OLDEST

**File:** `src/niri_pypc/api/event_stream.py:107-115`

The spec (Section 20) says "No silent event drop — both modes surface overflow visibility (log warning or exception)." The `DROP_OLDEST` path silently discards the oldest event with no logging. This violates the spec's observability requirement.

### SIG-4: `NiriClient.close()` is not truly async-safe

**File:** `src/niri_pypc/api/client.py:104-110`

```python
async def close(self) -> None:
    if not self._lifecycle.is_terminal:
        await self._lifecycle.transition_to(LifecycleState.CLOSED)
```

A `LifecycleManager` uses an `asyncio.Lock` internally, but `is_terminal` is read outside the lock. This is a TOCTOU race: another coroutine could transition the lifecycle between the `is_terminal` check and the `transition_to` call. In practice, for the one-connection-per-request client with no concurrent operations, this is low-risk, but it's technically unsound.

### SIG-5: `NiriConnectionBundle.__init__` directly mutates internal state

**File:** `src/niri_pypc/api/bundle.py:27`

```python
self._lifecycle._state = LifecycleState.READY  # skip to ready
```

This directly mutates the private `_state` attribute of the `LifecycleManager`, bypassing its transition validation. This couples the bundle to the internals of the lifecycle manager. If `LifecycleManager` adds validation or side effects on state changes, this would break. A proper approach would be either: (a) passing an initial state to the constructor, or (b) using a dedicated `transition_to` from INIT to READY.

### SIG-6: `decode_frame` in `connection.py` may hang indefinitely

**File:** `src/niri_pypc/transport/connection.py:115`

`self._reader.readuntil(b"\n")` will wait forever if the connection is alive but the server never sends a newline. The `timeout` parameter wraps this in `asyncio.wait_for`, which is correct when a timeout is provided, but the default for `read_frame` is `timeout=None`, meaning no timeout. Combined with the `event_read_timeout` defaulting to `None` in the config, a persistent connection that receives partial data (no trailing newline) will hang forever. This is by design for event streams but dangerous for command connections if a response is partial.

---

## 5. Moderate Issues

### MOD-1: `decode_externally_tagged` does not validate dict key type

**File:** `src/niri_pypc/types/codec.py:54`

```python
variant_name = cast(str, next(iter(data.keys())))
```

If a dict has a non-string key (e.g., an integer), this would raise a `TypeError` at runtime that is not caught. The spec assumes well-formed JSON, but defensive coding would check `isinstance(variant_name, str)`.

### MOD-2: `_encode_external_tag` returns inconsistent types for unit variants with `payload` field named `variant`

**File:** `src/niri_pypc/types/codec.py:111-115`

The newtype detection checks `list(model_fields.keys()) == ["payload"]`. Some generated models have a field called `payload` that wraps another model. The encode logic for newtypes does `variant.payload` and checks `isinstance(payload, BaseModel)` — if the payload is a `BaseModel`, it dumps it with `model_dump`. This is correct but could fail for newtype variants whose payload is a primitive that happens to be named something else, or where the variant class has a `payload` field that is not the actual wire payload. Since this is generated code, the risk is low, but the heuristic is fragile.

### MOD-3: Missing `CHANGELOG.md` or empty one

The spec (Section 27) requires release notes with upstream pin, schema/IR changes, etc. The repository has a `CHANGELOG.md` file referenced in `pyproject.toml` but it was not in the file listing — it may be empty or missing content.

### MOD-4: `tools/normalize_ir.py` uses `tomllib` (Python 3.11+) without version guard

**File:** `tools/normalize_ir.py:8`

`tomllib` is a stdlib module available only in Python 3.11+. The project requires Python 3.13+, so this is fine, but there is no explicit import guard or comment documenting the version dependency. If someone tried to run this on Python 3.10, they would get an `ImportError` with no helpful message.

### MOD-5: No `__all__` in `types/__init__.py`

**File:** `src/niri_pypc/types/__init__.py`

The wildcard import from `generated` makes all generated types available, but there is no explicit `__all__` list. This means `dir(niri_pypc.types)` includes everything from `generated`, which is large and includes internal helper classes like `UnknownEvent`, `UnknownReply`. Users doing `from niri_pypc.types import *` would get all of these.

### MOD-6: Schema hash verification is not performed at runtime

The IR contains `schema_hashes` and the `_metadata.py` has them, but neither the runtime code nor the generator verifies that the hashes match the actual schema files at import time or startup. This means a stale schema file would go undetected until the next regeneration. The spec mentions schema hashes for "drift detection" in CI, but runtime verification is absent.

### MOD-7: `encode_frame` does not handle non-JSON-serializable types

**File:** `src/niri_pypc/transport/framing.py:20`

`json.dumps` will raise `TypeError` for non-serializable types (e.g., `datetime`, `UUID`). This is not caught and wrapped into a `ProtocolError` or `EncodeError`. The function's docstring says `data: Any` but the implementation assumes JSON-serializability.

### MOD-8: `_run_reader` can exit without transitioning to CLOSED

**File:** `src/niri_pypc/api/event_stream.py:82-126`

If an unexpected exception occurs in the outer `try/except Exception: pass` (line 123-124), the `finally` block calls `_close_from_reader()`, which does transition to CLOSED. However, `_close_from_reader()` itself can raise (e.g., if `transition_to` raises `LifecycleError`), in which case the exception from `_close_from_reader` would propagate and the connection object could be left in an inconsistent state.

### MOD-9: `NiriEventStream.next()` timeout behavior with `None`

**File:** `src/niri_pypc/api/event_stream.py:138-183`

When `timeout=None`, `asyncio.wait_for` is called with `timeout=None`, which means it blocks indefinitely. This is the documented behavior when `event_read_timeout` is `None`. However, `asyncio.wait_for(None)` actually raises `ValueError` — you must pass `timeout=None` directly, not wrap it. Let me verify: `asyncio.wait_for(coro, timeout=None)` is valid and waits indefinitely. This is correct.

### MOD-10: `Connection.__init__` takes `Path` but `connect()` uses `str(socket_path)`

**File:** `src/niri_pypc/transport/connection.py:44`

`asyncio.open_unix_connection(str(socket_path))` converts Path to str. The `__init__` stores the Path, but `connect()` receives a Path and converts to str for `open_unix_connection`. This is consistent (str conversion happens at I/O boundary), but the `_socket_path` is stored as a `Path` while `read_frame` converts to `str` on error. Minor inconsistency.

---

## 6. Minor Issues & Style

### MIN-1: Ruff B009 — `getattr` with constant attribute value

**File:** `src/niri_pypc/types/codec.py:112`

```python
payload = getattr(variant, "payload")
```

Should be `payload = variant.payload`. Ruff correctly flags this. Since this is generated code, the fix should be applied to `tools/generate_types.py` as well.

### MIN-2: Ruff I001 — Import block unsorted in 7 generated files

**Files:** All files under `src/niri_pypc/types/generated/`

The import blocks have `from __future__ import annotations` before `typing.Any` and `pydantic` imports, but ruff's isort rules expect alphabetical grouping. Since these are generated files, the generator (`tools/generate_types.py`) should produce correctly sorted imports.

### MIN-3: `config.py` does lazy import of `ConfigError`

**File:** `src/niri_pypc/config.py:36`

```python
from niri_pypc.errors import ConfigError
```

This is a local import to avoid circular dependency, but since `errors.py` does not import from `config.py`, there is no circular dependency. The import can be moved to the top level.

### MIN-4: `NiriClient.connect` is a classmethod that returns an instance without going through `__init__` validation on reconnect

**File:** `src/niri_pypc/api/client.py:29-42`

`connect()` creates a client and validates the config by calling `resolve_socket_path()`. But on subsequent `request()` calls, `resolve_socket_path()` is called again. If the environment changes between calls (unlikely but possible), the socket path could change mid-lifecycle. This is minor since the config is frozen.

### MIN-5: `NiriTimeoutError` inherits from `TimeoutError` but may not be catchable as `TimeoutError` in all contexts

**File:** `src/niri_pypc/errors.py:29`

`asyncio.wait_for` raises `TimeoutError`, which is then caught and re-raised as `NiriTimeoutError`. Since `NiriTimeoutError` inherits from both `NiriError` and `TimeoutError`, code catching `TimeoutError` will catch it. However, in the `event_stream.py` (line 167), `TimeoutError` is caught and re-raised as `NiriTimeoutError` — this means code that catches `TimeoutError` around `stream.next()` would catch the re-wrapped `NiriTimeoutError`. This is correct, but the double-wrapping pattern could be confusing.

### MIN-6: `__anext__` in `NiriEventStream` delegates to `next()` but shadows the return type

**File:** `src/niri_pypc/api/event_stream.py:195-197`

```python
async def __anext__(self) -> BaseModel:
    event = await self.next()
    return event
```

The `__anext__` return type annotation says `BaseModel`, but the `AsyncIterator` type in `__aiter__` says `AsyncIterator[BaseModel]`. These are consistent, but it would be clearer if `next()` also had a more specific return type hint or if both used a type variable.

### MIN-7: Generated `models.py` contains unused imports

**File:** `src/niri_pypc/types/generated/models.py:9`

`from pydantic import BaseModel, ConfigDict, model_validator, model_serializer` — `model_validator` and `model_serializer` are only used in the enum root models (which are generated in separate files, not in `models.py`). These imports are present because the generator always emits them, even though `models.py` only defines structs and variant classes.

### MIN-8: `NiriConnectionBundle.close` re-raises only the first exception and loses the second

**File:** `src/niri_pypc/api/bundle.py:59-82`

```python
exc_caught = None
try:
    await self._client.close()
except Exception as exc:
    exc_caught = exc
try:
    await self._events.close()
except Exception as exc:
    if exc_caught is None:
        exc_caught = exc
```

If both `close()` calls raise exceptions, only the first one is propagated and the second is silently lost. Python 3.11+ has `ExceptionGroup` for this. At minimum, both exceptions should be logged.

---

## 7. Generated Code Quality

### 7.1: Models.py has many unused `model_config` imports

Every struct model in `models.py` includes `ConfigDict` via `model_config`, but several models have no explicit `model_config` (they inherit from `BaseModel`'s defaults). Wait, actually every model does have `model_config = ConfigDict(populate_by_name=True, strict=False)`. This is correct and matches the spec.

### 7.2: Generated enum variant names are unwieldy

Names like `FocusWindowDownOrColumnLeftAction` (11+ words concatenated) are common in `action.py`. While this matches the spec (Section 7, variant class naming `{VariantName}{EnumName}`), it makes for very long type names. This is a design choice, not a bug.

### 7.3: Generated `list[Any]` fields are opaque

Many generated models contain `list[Any]` fields (e.g., `WindowLayout.pos_in_scrolling_layout`, `Output.modes`). The IR maps these from `array<ref:Unknown>`. This means these fields are not type-safe. The spec acknowledges this with `ref:Unknown` mapping to `Any`.

### 7.4: Generated code uses `from __future__ import annotations` consistently

All generated files correctly include `from __future__ import annotations`, enabling forward references.

### 7.5: Determinism of generated output

The generation pipeline is deterministic:
- IR normalization sorts types, variants, and fields alphabetically.
- File generation iterates in sorted order.
- Hashes in headers are computed from content.
- The `verify-generated` tool confirms byte-for-byte match.

---

## 8. Tooling & Pipeline

### 8.1: Devenv scripts are well-organized

All five scripts (`export-schema`, `normalize-ir`, `generate-types`, `verify-generated`, `regen-all`) are present in `devenv.nix` and match the spec.

### 8.2: No CI configuration file present

There is no `.github/workflows/` directory or equivalent CI configuration. The spec (Section 26) describes CI quality gates that should be automated. This is expected for a project that hasn't been pushed to a CI system yet.

### 8.3: Schema exporter Rust binary is not present in the repo

The `tools/schema_exporter/` directory does not contain a `Cargo.toml` or `src/main.rs` in the repository. These would need to be created for new pin bumps. This is by design if the schemas are committed, but the absence means the full export pipeline cannot be run without creating the Rust binary first.

### 8.4: `verify_generated.py` spawns a subprocess instead of importing the generator

**File:** `tools/verify_generated.py:34-46`

The tool runs `python tools/generate_types.py` as a subprocess rather than importing and calling `main()` directly. This is a reasonable choice (avoids import side effects, matches production usage), but it means the generator's exit code and stderr must be properly handled — which they are.

---

## 9. Test Suite Analysis

### Coverage Summary (from pytest run):
- **Total statements:** 1402
- **Covered:** 1253 (89%)
- **Missed:** 149

### Coverage gaps:
- `src/niri_pypc/api/bundle.py` (80%) — lines 40, 45-47, 71-72, 75-77, 82
- `src/niri_pypc/api/event_stream.py` (80%) — BACKGROUND reader task error paths, backpressure FAIL_FAST, cancellation paths
- `src/niri_pypc/transport/connection.py` (85%) — timeout error, OSError paths
- `src/niri_pypc/types/codec.py` (91%) — unknown variant decode, encode error paths
- `src/niri_pypc/types/generated/models.py` (80%) — all the `_decode_external_tag` and `_encode_external_tag` methods

### Test quality observations:
- Type roundtrip tests are minimal — only test `VersionRequest`, `EventStreamRequest`, `WorkspaceActivated`, `WindowClosed`, and simple Reply variants. No tests for struct variants with fields, newtype variants, or Action enum.
- Event stream backpressure modes (`DROP_OLDEST` vs `FAIL_FAST`) are not tested separately.
- No test for `NiriClient` timeout override behavior.
- No test for `NiriTimeoutError` being catchable as `TimeoutError`.
- Integration tests only check happy paths and basic error handling.
- No test for the connection close race condition in the event stream.
- Live tests are properly gated by `NIRI_SOCKET`.

### Missing test categories from spec:
- **Transport tests** for partial/multi-frame reads and disconnect mid-frame are missing.
- **Transport tests** for malformed framing (missing newline) are missing.
- No tests for `NiriError` context fields (`operation`, `socket_path`, `retryable`, `state`).

---

## 10. Type Safety Gaps

### 10.1: Discriminated union narrowing doesn't propagate through Pydantic validators

When `Event.model_validate({"WorkspaceActivated": ...})` is called, the result type is `Event` — the type checker cannot narrow the `variant` field to `WorkspaceActivatedEvent`. This is inherent to Pydantic's runtime validation and is not a bug, but it means all event access requires either:
- Explicit `isinstance` checks (shown in `test_unknown_variants.py`)
- Acceptance of `BaseModel` type for variant payloads

### 10.2: `unwrap_reply` return type is `Any`

The `unwrap_reply` function returns `Any` because the reply payload types vary by request type. This is by design but means the caller loses all type information. A generic type parameter or overloads could improve this.

### 10.3: `NiriClient.request()` return type is `Any`

Similarly, the `request()` method returns `Any`, preventing type-safe access to response payloads without manual casting.

### 10.4: `Event.variant` type union includes `UnknownEvent`

For inbound events, the `Event.variant` field type includes `UnknownEvent` alongside all known event types. This means accessing event-specific fields always requires narrowing, even for known events. The generated code handles this correctly at runtime (decode dispatches to the right variant), but the type system does not reflect this.

---

## 11. Concurrency & Safety Concerns

### CONC-1: `NiriEventStream.close()` and `_run_reader` lifecycle race

Both can initiate the CLOSING→CLOSED transition. The `_run_reader` calls `_close_from_reader()` which transitions to CLOSING then CLOSED. The `close()` method also transitions to CLOSING then CLOSED. While `transition_to` is protected by an `asyncio.Lock`, the callers are not — `close()` checks `is_terminal` before acquiring the lock, creating a TOCTOU window. In practice, this is mitigated by the event stream being single-consumer.

### CONC-2: `_run_reader` cancellation handling

When `close()` cancels `_reader_task`, the `CancelledError` is caught by the outer `except Exception: pass` in `_run_reader`, and then `_close_from_reader()` is called from the `finally` block. This means the close path through cancellation is:
1. `close()` cancels task
2. `_run_reader` catches `CancelledError` in the outer except
3. `finally` calls `_close_from_reader()`
4. `_close_from_reader()` transitions to CLOSING → CLOSED

But `close()` also transitions to CLOSING → CLOSED after awaiting the task. This means there's a double-transition attempt. The first succeeds (INIT/READY → CLOSING → CLOSED in `_close_from_reader`), and the second in `close()` should find `is_terminal` is True and return early (line 201-202). This appears safe but is fragile.

### CONC-3: `_queue` and `_connection` are set without synchronization

In `NiriEventStream.connect()`, `self._queue` and `self._connection` are set sequentially without a lock. If another coroutine called `next()` between these assignments (unlikely since `connect` is a classmethod that returns before sharing the instance), it could encounter a partially-initialized state.

---

## 12. Positive Findings

1. **Clean separation of generated and hand-written code.** The architecture is well-maintained — no edits to generated files, clear boundaries.

2. **Deterministic generation pipeline.** The hash-based verification ensures reproducibility. The IR normalization sorts all types alphabetically.

3. **Proper error taxonomy.** All 9 error types from the spec are implemented with appropriate context fields (`operation`, `socket_path`, `retryable`, `state`, `remote_message`, `raw_payload`).

4. **Idempotent close semantics.** Both `UnixConnection.close()` and `NiriEventStream.close()` are correctly idempotent.

5. **Async context manager support.** All three API types (`NiriClient`, `NiriEventStream`, `NiriConnectionBundle`) properly implement `__aenter__`/`__aexit__`.

6. **Proper error isolation in bundle.** The `NiriConnectionBundle` correctly catches and suppresses secondary close errors (line 72, 75).

7. **Backpressure configuration.** Both `DROP_OLDEST` and `FAIL_FAST` modes are implemented, with correct queue management.

8. **Unknown variant handling.** Inbound unknown variants produce typed sentinel models carrying the raw payload for diagnostics. Outbound variants remain strict.

9. **Socket resolution precedence.** Correctly implements explicit → `NIRI_SOCKET` env → `ConfigError` chain.

10. **Comprehensive test coverage at 89%.** Integration tests with mock Unix socket servers provide good coverage of the API layer.

11. **README accurately reflects the API and architecture.** Code examples are correct and well-structured.

---

## 13. Recommendations Summary

### Must-Fix (Correctness/Spec Violations)

| # | Issue | File | Severity |
|---|-------|------|----------|
| 1 | Use type dispatch instead of class-name-prefix matching in `unwrap_reply` | `types/codec.py` | High |
| 2 | Add logging for dropped events in `DROP_OLDEST` mode | `api/event_stream.py` | High |
| 3 | Fix `encode_externally_tagged` to raise proper encode error, not `DecodeError` | `types/codec.py` | Medium |
| 4 | Prevent double-lifecycle-transition in `NiriEventStream` close path | `api/event_stream.py` | Medium |
| 5 | Validate dict key type in `decode_externally_tagged` | `types/codec.py` | Low |
| 6 | Wrap `json.dumps` errors in `encode_frame` with a typed exception | `transport/framing.py` | Low |

### Should-Fix (Code Quality)

| # | Issue | File | Severity |
|---|-------|------|----------|
| 7 | Fix ruff B009: replace `getattr(variant, "payload")` with `variant.payload` in code generator | `tools/generate_types.py` | Lint |
| 8 | Fix ruff I001: sort imports in generator output | `tools/generate_types.py` | Lint |
| 9 | Move lazy `ConfigError` import to top-level in `config.py` | `config.py` | Style |
| 10 | Add type-narrowing assertions in integration tests | `tests/integration/` | Type safety |
| 11 | Add `CHANGELOG.md` content per spec | Project root | Docs |
| 12 | Add schema hash runtime verification | `types/generated/__init__.py` or config | Robustness |

### Should-Add (Missing Coverage)

| # | Item |
|---|------|
| 13 | Transport tests for partial/multi-frame reads, disconnect mid-frame |
| 14 | Transport tests for malformed framing (missing newline, invalid JSON) |
| 15 | Tests for `NiriError` context fields |
| 16 | Tests for `NiriTimeoutError` catchable as `TimeoutError` |
| 17 | Tests for event stream backpressure modes |
| 18 | Tests for Action enum encode/decode roundtrip |
| 19 | Struct variant roundtrip tests (not just unit variants) |

### Nice-to-Have (Improvements)

| # | Item |
|---|------|
| 20 | Consider Pydantic `Discriminator`/`TaggedUnion` for better type narrowing |
| 21 | Add generic type parameters to `NiriClient.request()` and `unwrap_reply()` |
| 22 | Use `ExceptionGroup` for dual-exception propagation in `NiriConnectionBundle.close()` |
| 23 | Guard `tomllib` import with version check and helpful error |
| 24 | Add `__all__` to `types/__init__.py` to control public surface |

---

*Review complete. All findings are based on static analysis of the source code, schema documents, and test suite execution.*