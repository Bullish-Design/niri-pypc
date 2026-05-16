# Final Code Review: niri-pypc

**Date:** 2026-05-15
**Version:** 0.4.0
**Reviewer scope:** Every handwritten source file, all generated code, all tools, all tests, all configuration.

---

## Executive Summary

niri-pypc is a well-architected async IPC client library for the niri Wayland compositor. The codebase demonstrates strong engineering fundamentals: clean separation of concerns, a principled type system, deterministic code generation, comprehensive error taxonomy, and multi-tier testing. It is substantially above average for a library of this scope.

This review identifies opportunities to move from "good" to "exceptional" — eliminating remaining rough edges, tightening invariants, and addressing the few genuine architectural issues that remain.

**Overall Assessment: Strong.** The issues below are refinements, not red flags.

---

## Table of Contents

1. [Architecture & Design](#1-architecture--design)
2. [Type System & Code Generation](#2-type-system--code-generation)
3. [Transport Layer](#3-transport-layer)
4. [API Layer](#4-api-layer)
5. [Error Taxonomy](#5-error-taxonomy)
6. [Actions Module](#6-actions-module)
7. [Test Suite](#7-test-suite)
8. [Configuration & Packaging](#8-configuration--packaging)
9. [Documentation](#9-documentation)
10. [Summary of Findings](#10-summary-of-findings)

---

## 1. Architecture & Design

### 1.1 What Works Well

**Layered separation is clean and principled.**
The four-layer stack — `transport/` → `types/` → `api/` → `actions.py` — gives each concern a clear home. Dependencies flow strictly downward. No layer reaches past its immediate neighbor.

**One-connection-per-request for commands is the right call.**
For a compositor IPC protocol where requests are infrequent and latency-insensitive, the simplicity of a fresh socket per `request()` is the correct tradeoff. It eliminates connection pooling, reconnect logic, and multiplexing complexity — all of which would be over-engineering here.

**The `ExternallyTaggedEnum` / `ProtocolVariant` / `ProtocolModel` hierarchy is elegant.**
Metadata-driven variant dispatch via `__niri_wire_name__` and `__niri_variant_kind__` class vars avoids heuristics entirely. The cached `_variant_map()` provides O(1) lookup. Forward-compatible `UnknownEvent` is a thoughtful touch.

**The schema pipeline is production-grade.**
Rust exporter → JSON Schema → IR normalization → deterministic Python generation → CI verification is a rigorous pipeline. The hash-based provenance tracking (`_metadata.py`, `ir_hash`, `schema_hashes`) makes version skew immediately detectable.

### 1.2 Architectural Issues

#### ISSUE A-1: `LifecycleManager` is used only by `NiriEventStream` but lives in `runtime/`

The `runtime/` package contains exactly one module (`lifecycle.py`) used by exactly one consumer (`event_stream.py`). The `NiriClient` uses a simple `self._closed` boolean instead of the lifecycle manager, and the `NiriConnectionBundle` also uses its own `self._closed` boolean.

This creates two problems:
1. An entire package (`runtime/`) exists for a single 92-line file
2. The lifecycle abstraction isn't actually shared — only `NiriEventStream` uses it

**Recommendation:** Either (a) move `lifecycle.py` into `api/` (it's an API-layer concern), or (b) have `NiriClient` and `NiriConnectionBundle` also use `LifecycleManager` for consistency. Option (a) is simpler and more honest about the current usage.

#### ISSUE A-2: Dual codec paths — `base.py` and `codec.py` both encode/decode

The `ExternallyTaggedEnum._encode_root()` in `base.py` (lines 75-98) and `encode_externally_tagged()` in `codec.py` implement the same logic. The `_decode_root` validator in `base.py` calls through to `codec.decode_externally_tagged`, but `_encode_root` is self-contained and does NOT call `codec.encode_externally_tagged`.

This means:
- Decode path: `base.py` → `codec.py` (single source of truth)
- Encode path: `base.py` duplicates `codec.py` logic

```python
# base.py _encode_root — reimplements codec.encode_externally_tagged
@model_serializer(mode="plain")
def _encode_root(self) -> Any:
    root = self.root
    if isinstance(root, UnknownEvent):
        return {root.variant_name: root.raw_payload}
    ...
    if kind == "unit":
        return wire_name
    if kind == "newtype":
        ...
        return {wire_name: root.payload}
    if kind == "struct":
        return {wire_name: root.model_dump(mode="json")}
```

**Recommendation:** Have `_encode_root` delegate to `encode_externally_tagged(self.root)`, mirroring how `_decode_root` delegates to `decode_externally_tagged`. This makes `codec.py` the single source of truth for both directions.

#### ISSUE A-3: `types/__init__.py` re-exports everything via wildcard

```python
# types/__init__.py
from niri_pypc.types.generated import *  # noqa: F401,F403
```

This makes `niri_pypc.types` a wildcard re-export of every generated symbol (~200+ names). Users importing from `niri_pypc.types` get an unpredictable namespace. The README examples use `from niri_pypc.types import VersionRequest`, which works but relies on the wildcard chain.

**Recommendation:** This is a minor concern. The README examples are valid usage. But - `niri_pypc.types` should have an explicit `__all__` that curates the most commonly needed imports, leaving the full symbol set accessible via `niri_pypc.types.generated` for power users.

---

## 2. Type System & Code Generation

### 2.1 What Works Well

**Externally-tagged enum design is faithful to Rust serde conventions.**
The three-kind taxonomy (unit/newtype/struct) with explicit class vars is correct and complete. The `model_validator(mode="before")` approach for decode and `model_serializer(mode="plain")` for encode integrates cleanly with Pydantic v2.

**The IR normalization handles the full JSON Schema complexity.**
`canonical_type()` correctly prioritizes `$ref` > `anyOf` > `prefixItems` > `items` > `additionalProperties` > primitives. The `prefixItems` handling preserves tuple positional semantics. Nullable detection through `anyOf` with null type is correct.

**Generated code is clean and idiomatic.**
Despite being auto-generated, the output reads well. Each variant class is self-contained with its wire metadata. The `TypeAlias` unions provide clean discriminated union types. The `model_rebuild()` calls at module end correctly resolve forward references.

### 2.2 Issues

#### ISSUE T-1: `ExternallyTaggedEnum` has an unused `RootT` `TypeVar` alongside the generic parameter

```python
# base.py line 38
RootT = TypeVar("RootT", bound=ProtocolModel)

# line 41
class ExternallyTaggedEnum[RootT: ProtocolModel](RootModel[RootT]):
```

The class uses the new PEP 695 generic syntax (`class Foo[T: Bound]`) but also defines a module-level `TypeVar` with the same name on line 38. The class-level `[RootT: ProtocolModel]` creates its own scoped type parameter — it does NOT use the module-level `TypeVar`. The module-level `RootT` on line 38 is therefore dead code.

**Recommendation:** Remove the module-level `RootT = TypeVar(...)` on line 38. It's unused and potentially confusing.

#### ISSUE T-2: `_encode_root` accesses `root.payload` without Pydantic field validation

```python
# base.py line 90-91
if not hasattr(root, "payload"):
    raise TypeError(...)
return {wire_name: root.payload}
```

For newtype variants, this uses `hasattr` + direct attribute access rather than going through Pydantic's serialization. The `payload` field on newtype variants can itself be a complex model (e.g., `Action`, `Response`), but this code returns `root.payload` raw rather than serializing it.

Contrast with `codec.py` line 133:
```python
return {wire_name: _dump_value(value.payload)}
```

The `_dump_value` helper correctly calls `model_dump(mode="json")` for BaseModel payloads. The `base.py` version skips this.

**Impact:** For newtype variants whose payload is a Pydantic model (e.g., `OkReply` whose payload is `Response`), the `_encode_root` path will return the model *object* rather than its JSON-serializable dict. Pydantic's outer serialization may handle this, but it's fragile and inconsistent with the explicit serialization in `codec.py`.

**Recommendation:** This is another reason to consolidate to a single encode path (see Issue A-2). 

#### ISSUE T-3: `@cache` on `_variant_map()` classmethod is unbounded

```python
# base.py line 100-103
@classmethod
@cache
def _variant_map(cls) -> dict[str, type[ProtocolVariant]]:
    return {variant.__niri_wire_name__: variant for variant in cls.__niri_variants__}
```

`functools.cache` is an unbounded LRU cache. For a class method, this means one cache entry per subclass that calls it. With ~10 ExternallyTaggedEnum subclasses, this is fine in practice. However:

1. `@cache` on a classmethod caches with `cls` as the key. Since `cls` is a strong reference, this prevents garbage collection of the classes (not an issue for module-level classes, but worth noting).
2. The `@cache` decorator's type stubs don't perfectly interact with `@classmethod`, which can confuse some type checkers.

**Recommendation:** This is fine as-is for the current usage. No change needed, but `@functools.lru_cache(maxsize=None)` would be equivalent and more explicit about unbounded behavior.

#### ISSUE T-4: `PickedColor.rgb` is `list[float]` — could be `tuple[float, float, float]`

```python
# models.py line 334
class PickedColor(ProtocolModel):
    rgb: list[float]
```

The upstream Rust type is `Vec<f64>` which maps to `list[float]`, but semantically RGB is always 3 values. However, since this is auto-generated from the IR and the upstream schema doesn't use `prefixItems`, this is correct behavior — the generator faithfully reflects the upstream schema's imprecision.

**Recommendation:** No code change. This is a known limitation of the upstream schema. If niri's schema ever adds `prefixItems` for RGB, the pipeline will automatically generate `tuple[float, float, float]`.

#### ISSUE T-5: `normalize_ir.py` fallback to `"string"` is a silent data loss risk

```python
# normalize_ir.py line 111
return "string"  # final fallback
```

If `canonical_type()` falls through all branches, it silently returns `"string"`. This means an unrecognized schema shape would generate a `str` field rather than raising an error during IR normalization.

**Recommendation:** Replace the silent fallback with an explicit error:
```python
raise ValueError(f"Cannot determine canonical type for schema: {schema!r}")
```
If upstream ever adds a new schema pattern, this will surface as a clear normalization failure rather than silently generating wrong types.

#### ISSUE T-6: Generated `__init__.py` wildcard chain creates namespace pollution

```python
# generated/__init__.py
from niri_pypc.types.generated._metadata import *  # noqa: F401,F403
from niri_pypc.types.generated.models import *  # noqa: F401,F403
from niri_pypc.types.generated.action import *  # noqa: F401,F403
...
```

This exports every symbol from every generated module — including internal names like `ActionValue`, `ReplyValue`, `ResponseValue` (TypeAlias internals), individual variant classes like `OkReply`, `ErrReply`, and metadata constants like `UPSTREAM_CRATE`. Users doing `from niri_pypc.types import *` get ~250+ symbols.

**Recommendation:** Add `__all__` to generated `__init__.py` that explicitly lists the intended public API surface. The generator should emit this.

---

## 3. Transport Layer

### 3.1 What Works Well

**`UnixConnection` is a clean, minimal abstraction.**
It wraps exactly what's needed: connect, write frame, read frame, close. Error mapping is thorough and context-rich. Connection poisoning on timeout is correct — a timed-out `readuntil` leaves the stream in an indeterminate state.

**Frame protocol is correct.**
Newline-delimited JSON with exactly one trailing `\n` per frame. The `write_frame` normalization (line 77: `data if data.endswith(b"\n") else data + b"\n"`) is defensive. The `read_frame` stripping (line 151: `raw[:-1]`) is correct.

### 3.2 Issues

#### ISSUE TR-1: `read_frame` `max_size` parameter is misleading

```python
# connection.py lines 90-160
async def read_frame(self, *, max_size: int = 4 * 1024 * 1024, timeout: float | None = None) -> bytes:
```

The `max_size` parameter suggests it limits how much data is read, but the actual behavior is:
1. `readuntil(b"\n")` reads the entire frame into memory (bounded only by `stream_limit` from the asyncio stream)
2. Only AFTER the full frame is in memory, line 153 checks `if len(frame) > max_size`
3. `LimitOverrunError` from the asyncio stream is caught on line 133, but this is triggered by the stream's internal limit, not by `max_size`

The error message on line 136 says "Frame exceeds maximum {max_size} bytes before delimiter" — but this is not what happened. The `LimitOverrunError` was triggered by the asyncio stream's `limit` parameter (set via `stream_limit` in `connect`), not by `max_size`.

This means `max_size` and `stream_limit` are conflated. In `client.py` line 109:
```python
stream_limit=max(self._config.max_frame_size + 1, DEFAULT_STREAM_LIMIT),
```

The `+1` accounts for the newline, and `DEFAULT_STREAM_LIMIT` (64KB) is the asyncio default. But the `max_size` parameter on `read_frame` is redundant with the stream limit — both try to enforce frame size, but through different mechanisms.

**Recommendation:** Clarify the dual-enforcement model in documentation. The stream limit is the hard bound (prevents buffering), while `max_size` is the soft check (post-read validation). The error message on line 136 should accurately reflect the stream-level rejection. Consider whether the post-read `max_size` check is still needed given the stream limit enforcement.

#### ISSUE TR-2: `write_frame` doesn't enforce `max_size` on outbound frames

There's no size validation on writes. A caller could construct a multi-megabyte `ActionRequest` and `write_frame` would happily send it. The compositor would likely reject it, but the transport layer doesn't protect against accidentally serializing huge payloads.

**Recommendation:** This is low-priority. Outbound frames are library-constructed and unlikely to be huge. However, a `max_size` parameter on `write_frame` would provide symmetry.

#### ISSUE TR-3: `close()` swallows all `OSError` silently

```python
# connection.py lines 168-177
async def close(self) -> None:
    if self._closed:
        return
    self._closed = True
    try:
        self._writer.close()
        await self._writer.wait_closed()
    except OSError:
        pass
```

This is correct for an idempotent close — you don't want errors during cleanup to propagate. However, catching all `OSError` also silences unexpected errors (e.g., permission errors, filesystem issues) that might indicate real problems.

**Recommendation:** This is fine as-is. Close operations should be best-effort. The `self._closed = True` is set before the try block, ensuring the connection is marked closed even if `wait_closed()` fails.

---

## 4. API Layer

### 4.1 What Works Well

**`NiriClient` is pleasantly simple.**
The entire class is 136 lines with 13 overloads for type precision. The one-connection-per-request pattern means there's no connection state to manage. The `request()` method is a clean pipeline: serialize → connect → write → read → deserialize → unwrap.

**`NiriEventStream` lifecycle management is thorough.**
The state machine (`INIT → CONNECTING → READY → CLOSING → CLOSED`) with the background reader task, bounded queue, and configurable backpressure is a solid design. Terminal condition signaling via `asyncio.Event` + `_ClosedItem`/`_ErrorItem` sentinels is clean.

**`NiriConnectionBundle` correctly handles atomicity.**
The try/except in `open()` that closes the client if the event stream fails is correct. The `close()` method's first-error preservation is reasonable.

### 4.2 Issues

#### ISSUE API-1: `NiriClient.create()` resolves socket path eagerly, but `request()` resolves it again

```python
# client.py lines 53-61
@classmethod
def create(cls, config: NiriConfig | None = None) -> NiriClient:
    if config is None:
        config = NiriConfig()
    config.resolve_socket_path()  # Eagerly validate
    return cls(config)

# client.py line 103
async def request(self, req: RequestValue, ...) -> ResponseValue:
    socket_path = self._config.resolve_socket_path()  # Re-resolve every time
```

The eager resolution in `create()` is a validation check — it ensures the socket path is available at creation time. But `resolve_socket_path()` is called again in every `request()`. Since `NiriConfig` is frozen, the result will always be the same (unless `NIRI_SOCKET` env var changes between calls, which is an edge case).

**Recommendation:** Cache the resolved socket path in the client instance:
```python
def __init__(self, config: NiriConfig) -> None:
    self._config = config
    self._socket_path = config.resolve_socket_path()
    self._closed = False
```
This avoids repeated env var lookups and makes the behavior consistent with the eager validation.

#### ISSUE API-2: `NiriEventStream._close_reader_resources` has complex state transitions

```python
# event_stream.py lines 187-207
async def _close_reader_resources(self) -> None:
    if self._lifecycle.state == LifecycleState.CLOSED:
        return
    try:
        await self._lifecycle.transition_to(LifecycleState.CLOSING)
    except LifecycleError:
        if self._lifecycle.state != LifecycleState.CLOSING:
            return

    ...

    try:
        await self._lifecycle.transition_to(LifecycleState.CLOSED)
    except LifecycleError:
        pass
```

This method is called from the reader task's `finally` block. The dual `try/except LifecycleError` with state checks is defensive but hard to reason about. The method must handle being called when:
- The state is already CLOSING (explicit `close()` was called first)
- The state is already CLOSED (shouldn't happen, but guarded)
- The state is READY (normal reader exit)

The conditional `if self._lifecycle.state != LifecycleState.CLOSING: return` on line 193 means: "if the transition failed and we're not already in CLOSING, bail out." This handles the race where explicit `close()` already transitioned to CLOSING.

**Recommendation:** Add a comment explaining the state machine contract of this method. The logic is correct but non-obvious.

#### ISSUE API-3: `NiriEventStream.close()` and `_close_reader_resources()` can race

Both `close()` (explicit) and `_close_reader_resources()` (reader task cleanup) manipulate the lifecycle state and connection. The `LifecycleManager`'s asyncio.Lock serializes state transitions, but the operations between transitions (cancelling the reader task, closing the connection) are not under the lock.

Scenario:
1. `close()` transitions to CLOSING
2. `close()` cancels reader task
3. Reader task's `finally` block calls `_close_reader_resources()`
4. `_close_reader_resources()` tries transition to CLOSING (fails — already CLOSING)
5. `_close_reader_resources()` sees state is CLOSING, proceeds to close connection
6. `close()` also tries to close connection

Both `close()` and `_close_reader_resources()` call `self._connection.close()`, which is guarded by `if not self._connection.is_closed`. Since `UnixConnection.close()` is idempotent and `is_closed` is set before the actual close, this race is safe in practice.

**Recommendation:** This is safe but worth documenting. The idempotency of `UnixConnection.close()` and the `is_closed` guard make this race benign. Consider adding a brief comment in `close()` noting this invariant.

#### ISSUE API-4: `NiriEventStream.next()` has three separate terminal checks

```python
# event_stream.py lines 209-256
async def next(self, ...) -> EventValue:
    if self._queue is None:                          # Check 1: not connected
        raise InternalError(...)
    if self._terminal_event.is_set() and self._queue.empty():  # Check 2: terminal + drained
        ...
    if self._lifecycle.is_terminal:                  # Check 3: lifecycle terminal
        ...
    # Then read from queue
    item = await asyncio.wait_for(self._queue.get(), timeout=read_timeout)
    # Then check item type for terminal sentinels    # Check 4: queue sentinel
```

Four separate terminal detection mechanisms:
1. `_queue is None` (never connected)
2. `_terminal_event.is_set() and _queue.empty()` (terminal + drained)
3. `_lifecycle.is_terminal` (state machine)
4. `_ErrorItem` / `_ClosedItem` from queue (sentinel)

This redundancy is defensive, but the `_terminal_event` check on line 215 and the `is_terminal` check on line 223 partially overlap — both detect that the stream is done. The difference is that check 2 only fires when the queue is empty (drained), while check 3 fires regardless of queue state.

**Recommendation:** This is correct but could be simplified. The `_terminal_event` + `_queue.empty()` check exists to avoid blocking on an empty queue when the terminal has been signaled. This is a subtle race prevention. Consider unifying into a single guard:

```python
if self._lifecycle.is_terminal and self._queue.empty():
    # All events consumed and stream is done
    ...
```

But this would require ensuring `is_terminal` is set atomically with the terminal cause, which the current `_terminal_event` provides. The current code is correct; just complex.

#### ISSUE API-5: `NiriConnectionBundle` doesn't expose `is_closed`

`NiriClient` has `is_closed`, `NiriEventStream` has `_lifecycle.is_terminal`, but `NiriConnectionBundle` has no public way to check if it's been closed. The `_closed` field is private.

**Recommendation:** Add `@property is_closed(self) -> bool` for consistency.

#### ISSUE API-6: `NiriClient` overloads don't match all response types

The overload signatures in `client.py` map request types to response types. But:
- `ReturnErrorRequest` is overloaded to return `HandledResponse` — but this request specifically asks the compositor to return an error. The actual response is `ErrReply`, which `unwrap()` will raise as `RemoteError`. So the overload signature is technically correct (if the compositor somehow returns Ok), but the request's purpose is to test error handling.

**Recommendation:** This is technically correct but could use a docstring note explaining that `ReturnErrorRequest` is a diagnostic tool that will normally raise `RemoteError`.

---

## 5. Error Taxonomy

### 5.1 What Works Well

**The error hierarchy is well-stratified.**
Nine error types with clear delineation. `NiriTimeoutError` correctly inherits from both `NiriError` and `TimeoutError` for `except TimeoutError` compatibility. `DecodeError` truncates large payloads (1024 chars). `RemoteError` carries the compositor's error message.

**Error context is rich.**
Every error can carry `operation`, `socket_path`, `retryable`, and `cause`. This is excellent for debugging IPC issues.

### 5.2 Issues

#### ISSUE E-1: `NiriError.__init__` uses `cause` parameter AND `raise ... from exc` pattern

Throughout the codebase, errors are raised with both:
```python
raise TransportError("...", cause=exc) from exc
```

The `cause` attribute on `NiriError` and Python's `__cause__` (from `raise ... from`) carry the same information. This is redundant but not harmful — it means users can access the original exception via either `err.cause` or `err.__cause__`.

**Recommendation:** This is fine. The explicit `cause` field is more discoverable in the API surface than `__cause__`, and having both doesn't hurt.

#### ISSUE E-2: `EncodeError` is defined but only used in `codec.py`

`EncodeError` appears in:
- `errors.py` (definition)
- `codec.py` (used in `encode_externally_tagged`)
- `__init__.py` (re-exported)

It's never raised by `base.py`'s `_encode_root` (which raises `TypeError` and `ValueError` instead). This means users who catch `EncodeError` won't catch errors from the Pydantic serialization path.

**Recommendation:** Standardize on `EncodeError` for all encoding failures. Replace the `TypeError` and `ValueError` raises in `_encode_root` with `EncodeError`. This makes the error taxonomy complete — all niri-pypc errors are `NiriError` subclasses.

#### ISSUE E-3: `InternalError` has no structured context

```python
class InternalError(NiriError):
    """Impossible internal state — indicates a bug in niri-pypc."""
```

It inherits `operation` from `NiriError` but doesn't carry any additional context about the internal state that was violated. It's raised in two places:
1. `event_stream.py:211` — "Event stream not connected"
2. `event_stream.py:253` — "Unexpected queue item type"

**Recommendation:** This is fine for now. The error messages are descriptive enough. If more `InternalError` sites are added, consider a structured `details` field.

---

## 6. Actions Module

### 6.1 What Works Well

**The builder API is comprehensive and ergonomic.**
137 builder functions covering all non-debug niri actions. The `_wrap()` helper and `_coerce_workspace_ref()` keep the implementation DRY. The `spawn_sh()` safety warning is appropriate.

**The `__all__` export list is meticulously organized.**
Grouped by category with comment headers. Every public builder is explicitly listed.

**Workspace reference coercion is user-friendly.**
```python
focus_workspace(1)          # int → Id variant
focus_workspace("main")     # str → Name variant
focus_workspace(ref)        # WorkspaceReferenceArg pass-through
```

### 6.2 Issues

#### ISSUE ACT-1: `actions.py` shadows the builtin `id` in multiple function signatures

```python
def focus_window(id: int) -> ActionRequest:  # shadows builtin `id`
def close_window(id: int | None = None) -> ActionRequest:  # shadows builtin `id`
```

Over 30 builder functions use `id` as a parameter name, shadowing Python's builtin `id()`. This is a common Python convention for domain-specific APIs and is flagged by B006 in some linters, but ruff's selected rules don't catch it.

**Recommendation:** This is acceptable. The parameter name matches the niri IPC field name (`id`), and renaming to `window_id` would diverge from the wire protocol. The shadowing is harmless in these small function bodies.

#### ISSUE ACT-2: `quit()` shadows the builtin `quit`

```python
def quit(skip_confirmation: bool = False) -> ActionRequest:
```

This shadows Python's builtin `quit()`. Unlike `id`, `quit()` is commonly used interactively and its shadowing could confuse users in REPL sessions.

**Recommendation:** This is borderline. The function name matches the niri action name. Users can still access the builtin via `builtins.quit()`. Since this is in a namespace (`niri_pypc.actions.quit`), the shadowing only matters if someone does `from niri_pypc.actions import *`. The `__all__` list does include it. Consider documenting this or providing an alias like `quit_niri()`.

#### ISSUE ACT-3: `_coerce_workspace_ref` raises `TypeError` instead of a niri-pypc error

```python
# actions.py line 380
raise TypeError(f"Expected int, str, or WorkspaceReferenceArg, got {type(ref).__name__}")
```

All other niri-pypc errors inherit from `NiriError`. This `TypeError` breaks the invariant that library errors are always `NiriError` subclasses.

**Recommendation:** This could go either way. `TypeError` is semantically correct for a type mismatch in a function argument. It follows Python convention (similar to how `int()` raises `TypeError` for non-numeric inputs). However, for consistency, wrapping it in an `EncodeError` or keeping `TypeError` but documenting the deviation is reasonable. I'd leave it as `TypeError` — it's a programmer error, not a runtime failure.

#### ISSUE ACT-4: No docstrings on most builder functions

Only 7 of 137 builders have docstrings: `spawn`, `spawn_sh`, `focus_workspace`, `move_window_to_workspace`, `move_column_to_workspace`, `set_workspace_name`, `unset_workspace_name`, and `quit`. The remaining 130 have no documentation.

For simple zero-parameter builders like `focus_column_left()`, the function name is self-documenting. But for builders with parameters like `set_window_height(change, id)` or `screenshot_screen(show_pointer, write_to_disk, path)`, the parameter semantics aren't obvious.

**Recommendation:** At minimum, add docstrings to builders that have non-obvious parameters. The zero-parameter builders are fine without.

#### ISSUE ACT-5: Import block is extremely long (153 lines)

The import section of `actions.py` (lines 11-175) imports ~140 symbols from generated types. This is unavoidable given the 1:1 mapping between builders and action variants, but it dominates the file.

**Recommendation:** This is inherent to the design and not a real problem. The imports are sorted and grouped. An alternative would be `from niri_pypc.types.generated.action import *` with an `__all__` check, but explicit imports are better for tooling.

---

## 7. Test Suite

### 7.1 What Works Well

**Multi-tier testing strategy is excellent.**
- Unit tests for codec, lifecycle, config
- Contract tests for transport and type system
- Integration tests with mock servers
- E2E tests with nested niri instances
- Live tests against real compositor

**The mock server fixtures are well-designed.**
`conftest.py` provides `mock_command_server`, `mock_event_server`, and `mock_unified_server` with clean control dicts. The fixtures handle setup/teardown correctly.

**The nested niri harness is impressively robust.**
Session-scoped fixtures, cross-process locking for visible mode, scenario-based configuration, artifact capture on failure — this is production-grade test infrastructure.

**Action builder completeness meta-test.**
`test_actions.py` maintains an `ALL_BUILDERS` list and parametrizes over it, ensuring every builder is tested for basic functionality and wire format. This catches missing test coverage automatically.

### 7.2 Issues

#### ISSUE TEST-1: Type roundtrip tests cover only ~10% of variants

`test_roundtrip.py` tests 6 specific cases: VersionRequest, EventStreamRequest, WorkspaceActivatedEvent, WindowClosedEvent, Ok+Version reply, Err reply. There are 15 request variants, 16 event variants, and 13 response variants — the vast majority are untested for roundtrip fidelity.

`test_reply_roundtrip.py` adds more coverage for replies (Outputs, FocusedOutput, FocusedWindow, Version, Err, Windows, Layers, KeyboardLayouts) but still doesn't cover OverviewState, PickedColor, PickedWindow, OutputConfigChanged, or Workspaces responses.

**Recommendation:** Add parametrized roundtrip tests that cover all variants. Use representative payloads for each. This is the highest-value test investment.

#### ISSUE TEST-2: No tests for concurrent event stream operations

The event stream has a background reader task and a consumer-facing `next()`/`__anext__()`. There are no tests for:
- Multiple coroutines calling `next()` simultaneously
- Calling `close()` while `next()` is blocking
- Reader task error while `next()` is waiting
- Rapid open/close cycles

**Recommendation:** Add concurrent operation tests. These are the most likely source of real-world bugs.

#### ISSUE TEST-3: Integration tests have loose assertions

```python
# test_nested_niri_basic.py
assert len(workspaces_response.payload) >= expectations.workspace_count
```

Using `>=` instead of `==` makes tests pass even if extra workspaces exist. This is pragmatic for dynamic compositor state, but reduces test precision.

**Recommendation:** Where possible, use exact assertions. For dynamic state, document why inexact assertions are necessary.

#### ISSUE TEST-4: No tests for `DecodeError.MAX_PAYLOAD_EXCERPT` truncation

`DecodeError.__init__` truncates `raw_payload` to 1024 chars, but no test verifies this behavior.

**Recommendation:** Add a unit test that creates a `DecodeError` with a payload > 1024 chars and verifies truncation.

#### ISSUE TEST-5: `test_edge_cases.py` only tests Request, not Reply or Event

```python
# test_edge_cases.py - only tests Request parsing
def test_none_request_raises():
    with pytest.raises(DecodeError):
        Request.model_validate_json("null")
```

**Recommendation:** Add equivalent edge case tests for `Reply`, `Response`, and `Event` parsing.

#### ISSUE TEST-6: No tests for `actions._coerce_workspace_ref` error path

The `TypeError` raised when an invalid type is passed to `_coerce_workspace_ref` is untested.

**Recommendation:** Add:
```python
def test_coerce_workspace_ref_invalid_type():
    with pytest.raises(TypeError, match="Expected int, str"):
        _coerce_workspace_ref(3.14)
```

#### ISSUE TEST-7: `mock_event_server` handler closes writer immediately after sending events

```python
# conftest.py line 115
writer.close()
```

This means the mock server closes the connection immediately after sending all configured events, which triggers a `TransportError` (EOF) in the event stream reader. Tests that rely on the stream staying open must work around this.

**Recommendation:** This is by design — the mock server simulates a finite event stream. But it limits testing of long-lived stream behavior. Consider adding a `mock_persistent_event_server` fixture that stays open until explicitly told to close.

---

## 8. Configuration & Packaging

### 8.1 What Works Well

**`pyproject.toml` is clean and complete.**
Hatchling build system, proper src layout, PEP 561 marker, sensible ruff configuration, pytest-asyncio auto mode. The generated types are correctly excluded from ruff formatting and ty type checking.

**The devenv.nix setup provides reproducible environments.**
Development commands are accessed via `devenv shell --` prefix, ensuring consistent tooling.

### 8.2 Issues

#### ISSUE CFG-1: `pyproject.toml` `addopts` includes `--cov` by default

```toml
addopts = "-q --cov=niri_pypc --cov-report=term-missing"
```

Coverage measurement is always on, which slows down test runs and can interfere with debugging (e.g., coverage instrumentation can mask certain errors, and `--cov` is incompatible with some debuggers).

**Recommendation:** Remove `--cov` from `addopts` and use it explicitly: `pytest --cov=niri_pypc`. Or use `[tool.coverage.run]` configuration with `--no-cov` override support.

#### ISSUE CFG-2: `pydantic>=2.12.5` lower bound may be too specific

Pinning to `>=2.12.5` means very recent Pydantic 2.x. The library uses standard Pydantic v2 features (`model_validator`, `model_serializer`, `RootModel`, `ConfigDict`). These were available since Pydantic 2.0. The `>=2.12.5` pin may unnecessarily restrict compatibility.

**Recommendation:** Test with the earliest Pydantic 2.x that supports all used features. If 2.0 or 2.1 works, lower the bound. This improves compatibility with other projects that pin older Pydantic versions.

#### ISSUE CFG-3: `README.md` examples use `result.variant.payload` which doesn't match the API

```python
# README.md line 40
result = await client.request(VersionRequest())
print(result.variant.payload)  # e.g., "25.11"
```

The `request()` method returns a `ResponseValue` (e.g., `VersionResponse`), which is a `ProtocolVariant`. There's no `.variant` attribute — the `VersionResponse` IS the variant. The payload is accessed via `result.payload`.

Correct code:
```python
result = await client.request(VersionRequest())
print(result.payload)  # "25.11"
```

Similarly, line 75:
```python
version = await bundle.client.request(VersionRequest())
print(f"Version: {version.variant.payload}")
```

Should be:
```python
print(f"Version: {version.payload}")
```

**Recommendation:** Fix the README examples. This is a user-facing bug.

---

## 9. Documentation

### 9.1 What Works Well

**README is comprehensive.**
Architecture section, configuration table, error taxonomy, regeneration pipeline, development commands, safety rules, incident recovery — all clearly documented.

**Module docstrings are present and useful.**
Every handwritten module has a one-line docstring that accurately describes its purpose.

### 9.2 Issues

#### ISSUE DOC-1: README examples are incorrect (see CFG-3 above)

All three usage examples reference `.variant.payload` which doesn't exist.

#### ISSUE DOC-2: No API reference documentation

There's no generated API docs (e.g., Sphinx, pdoc). Users must read source code to discover the full API surface. For a typed library with a complex type hierarchy, generated docs would be valuable.

**Recommendation:** Low priority for alpha, but worth adding before 1.0.

#### ISSUE DOC-3: `codec.py` doesn't document the `_dump_value` function

```python
def _dump_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value
```

This helper is critical for correct newtype serialization but has no docstring or comment explaining why it's needed (answer: newtype payloads can be Pydantic models that need JSON serialization).

**Recommendation:** Add a one-line docstring.

---

## 10. Summary of Findings

### By Severity

#### High Priority (correctness / user-facing)
| ID | Issue | Location |
|---|---|---|
| CFG-3 / DOC-1 | README examples use non-existent `.variant.payload` | `README.md` |
| T-2 | `_encode_root` doesn't serialize newtype payloads through `_dump_value` | `types/base.py:90` |
| A-2 | Dual encode paths — `base.py` and `codec.py` diverge | `types/base.py`, `types/codec.py` |
| T-5 | `normalize_ir.py` silent fallback to `"string"` for unknown schemas | `tools/normalize_ir.py:111` |

#### Medium Priority (consistency / maintainability)
| ID | Issue | Location |
|---|---|---|
| T-1 | Dead `RootT` TypeVar in `base.py` | `types/base.py:38` |
| E-2 | `_encode_root` raises `TypeError`/`ValueError` instead of `EncodeError` | `types/base.py:82,92,98` |
| API-1 | `NiriClient.request()` re-resolves socket path every call | `api/client.py:103` |
| API-5 | `NiriConnectionBundle` missing `is_closed` property | `api/bundle.py` |
| TEST-1 | Type roundtrip tests cover only ~10% of variants | `tests/types/` |
| TEST-2 | No concurrent event stream operation tests | `tests/api/` |
| A-1 | `runtime/` package exists for single file used by single consumer | `runtime/lifecycle.py` |

#### Low Priority (polish / minor improvements)
| ID | Issue | Location |
|---|---|---|
| T-6 | Generated `__init__.py` exports ~250+ symbols without `__all__` | `types/generated/__init__.py` |
| A-3 | `types/__init__.py` wildcard re-export | `types/__init__.py` |
| ACT-4 | Most action builders lack docstrings | `actions.py` |
| CFG-1 | `--cov` always on in `addopts` | `pyproject.toml` |
| TEST-4 | No test for `DecodeError` payload truncation | `tests/` |
| TEST-5 | Edge case tests only cover Request, not Reply/Event | `tests/types/` |
| TEST-6 | `_coerce_workspace_ref` error path untested | `tests/` |
| TR-1 | `read_frame` `max_size` vs `stream_limit` confusion | `transport/connection.py` |

### What's Excellent (no action needed)

- **Externally-tagged enum type system** — faithful to Rust serde, metadata-driven, forward-compatible
- **Schema pipeline** — deterministic, hash-verified, CI-enforced
- **Error taxonomy** — nine distinct types with rich context, all inheriting `NiriError`
- **One-connection-per-request client** — correct simplicity tradeoff
- **Event stream lifecycle** — state machine with terminal signaling and configurable backpressure
- **Action builder completeness** — 137 functions covering all non-debug actions, with meta-test
- **Test infrastructure** — mock servers, nested harness, cross-process locking, artifact capture
- **Transport layer** — clean framing, connection poisoning on timeout, idempotent close

---

## Architecture Diagram (current state)

```
                    ┌─────────────────────────────────────────────┐
                    │              User Code                       │
                    └───────────┬─────────────┬───────────────────┘
                                │             │
                    ┌───────────▼───┐   ┌─────▼──────────────────┐
                    │  actions.py   │   │  niri_pypc.__init__    │
                    │  (builders)   │   │  (public re-exports)   │
                    └───────┬───────┘   └────────────────────────┘
                            │
         ┌──────────────────┼──────────────────────┐
         │                  │                      │
    ┌────▼────┐     ┌───────▼──────┐      ┌───────▼───────┐
    │ client  │     │ event_stream │      │    bundle     │
    └────┬────┘     └──────┬───────┘      └───────────────┘
         │                 │
         │          ┌──────▼───────┐
         │          │  lifecycle   │
         │          └──────────────┘
         │                 │
    ┌────▼─────────────────▼───────┐
    │     transport/connection     │
    └──────────────────────────────┘
                    │
    ┌───────────────▼──────────────┐
    │      types/ (base + codec)   │
    ├──────────────────────────────┤
    │   types/generated/ (models)  │
    └──────────────────────────────┘
                    │
    ┌───────────────▼──────────────┐
    │     errors.py + config.py    │
    └──────────────────────────────┘
```

---

*End of review.*
