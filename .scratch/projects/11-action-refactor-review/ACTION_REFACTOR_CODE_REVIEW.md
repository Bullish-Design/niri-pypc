# niri-pypc Final Code Review

**Reviewer:** Claude Opus 4.6
**Date:** 2026-05-14
**Version Reviewed:** 0.3.1 (commit d91cb22)
**Scope:** Full library — transport, types, codec, API, actions, codegen tools, tests

---

## Executive Summary

niri-pypc is a well-architected async Python IPC client library for the niri Wayland compositor. The codebase demonstrates strong engineering fundamentals: a clean layered architecture, a robust code generation pipeline, comprehensive error handling, and good test coverage (96% line coverage, all tests passing). The recently added action builder module (137 builders, 14 enum helpers) is well-designed and thoroughly tested.

The library is in good shape for its alpha stage. The issues identified below are mostly minor design refinements and hardening opportunities rather than correctness bugs.

**Overall Rating: Strong** — production-viable for its stated scope with minor improvements recommended.

---

## Table of Contents

1. [Architecture Review](#1-architecture-review)
2. [Type System & Code Generation](#2-type-system--code-generation)
3. [Transport Layer](#3-transport-layer)
4. [API Layer](#4-api-layer)
5. [Action Builder Module](#5-action-builder-module)
6. [Error Handling](#6-error-handling)
7. [Test Suite](#7-test-suite)
8. [Code Quality & Style](#8-code-quality--style)
9. [Security Considerations](#9-security-considerations)
10. [Findings Summary](#10-findings-summary)
11. [Recommendations](#11-recommendations)

---

## 1. Architecture Review

### Strengths

- **Clean layered separation**: transport → types/codec → API → actions. Each layer has a single responsibility and minimal coupling to adjacent layers.
- **Deterministic code generation pipeline**: Rust schema → JSON Schema → normalized IR → Pydantic models. The pipeline is well-documented with hash-based provenance tracking (`_metadata.py`).
- **Three-client pattern** is appropriate: `NiriClient` (stateless request-per-connection), `NiriEventStream` (persistent + background reader), `NiriConnectionBundle` (coordinator). Each serves a distinct use case.
- **Forward compatibility** via `UnknownEvent` sentinel — the event stream gracefully handles new event types from future niri versions without crashing.
- **Frozen models** everywhere (`frozen=True`, `extra="forbid"`) — prevents accidental mutation and rejects unexpected fields.

### Concerns

**A-1: LifecycleManager may be over-engineered for NiriClient**
`NiriClient` uses a simple `_closed` boolean flag rather than `LifecycleManager`. This is actually the right call — `NiriClient` has trivial lifecycle (open/closed). However, `NiriEventStream` uses `LifecycleManager` which adds an `asyncio.Lock` for every state transition. Since the event stream runs in a single event loop (not multi-threaded), the lock adds overhead without providing meaningful safety beyond what single-threaded asyncio already guarantees.

*Severity: Low / Design Note*
*The lock is not wrong — it's defensive. But we should examine fixing for performance-sensitive paths.*

**A-2: NiriClient.connect() is synchronous but validates socket eagerly**
`NiriClient.connect()` calls `config.resolve_socket_path()` eagerly (which can raise `ConfigError`) but doesn't actually open a connection — connections are per-request. This is fine for fail-fast validation, but the method name `connect` is misleading since no connection is established.

*Severity: Low / Naming*
*Rename to `NiriClient.create()` and document that it only validates config.*

---

## 2. Type System & Code Generation

### Strengths

- **Metadata-driven codec** (`__niri_wire_name__`, `__niri_variant_kind__`) is elegant and eliminates field-shape heuristics. This is a significant improvement over the previous approach.
- **Three variant kinds** (unit, newtype, struct) map cleanly to Rust's serde externally-tagged enum format.
- **ExternallyTaggedEnum generic** is a clean abstraction — a single `RootModel[T]` subclass handles all encode/decode logic via `model_validator`/`model_serializer`.
- **`_variant_map()` is cached** via `@cache` — good for avoiding repeated dict construction.
- **IR normalization** handles complex JSON Schema constructs well: nullable refs, `prefixItems` → tuples, `additionalProperties` → maps, nested `anyOf`.

### Concerns

**T-1: `@cache` on `_variant_map()` is a classmethod — potential memory leak**
`functools.cache` on a classmethod creates an unbounded cache keyed by `cls`. Since there are a fixed number of `ExternallyTaggedEnum` subclasses, this is not a practical problem — but `@cache` prevents the class objects from being garbage collected. Using `@lru_cache(maxsize=None)` would be equivalent but more explicit about intent.

*Severity: Very Low / Nitpick*
*Examine pros/cons/implications/opportunities*

**T-2: `_decode_root` checks `isinstance(data, cls)` first — prevents re-wrapping**
Line 50 of `base.py`: `if isinstance(data, cls): return data`. This is correct for preventing double-wrapping, but it silently accepts an instance of a *different* `ExternallyTaggedEnum` subclass if it happens to be a subtype. Since none of the generated enums inherit from each other, this is safe in practice.

*Severity: Very Low / Theoretical*

**T-3: Newtype variant serialization uses `.payload` attribute access**
In `_encode_root` (base.py:90): `return {wire_name: root.payload}`. This assumes all newtype variants have a `payload` field. This invariant is enforced by the code generator, but there's no runtime assertion if a hand-written variant accidentally omits it. The error would be an `AttributeError` rather than a descriptive `EncodeError`.

*Severity: Low*
*Consider `getattr(root, 'payload', ...)` with a descriptive error, or leave as-is since variants are generated.*

**T-4: `physical_size` and `WindowLayout` spatial fields use `list[int]` / `list[float]` instead of tuples**
`Output.physical_size: list[int] | None` and `WindowLayout.tile_size: list[float]` etc. are semantically fixed-length (e.g., `[width, height]` or `[x, y]`). The IR normalizer collapses homogeneous `prefixItems` to `array<T>` (normalize_ir.py:127), which generates `list[T]` instead of `tuple[T, T]`. This loses the fixed-length semantic at the Python level.

*Severity: Medium / Schema Fidelity*
*The normalizer's heuristic (same-typed prefixItems → array) is lossy. `[int, int]` → `list[int]` means the Python type allows `[1, 2, 3]` where the wire format expects exactly 2 elements. Update to enforce preserving tuple types for homogeneous fixed-length arrays, or adding length validation.*

**T-5: Generated models have `pass` in zero-field struct variant classes**
Classes like `FocusColumnLeftAction` have `pass` as their only body. This is standard Python, but it means the struct serializes to `{"FocusColumnLeft": {}}` (an empty dict). The Rust side should accept this, but it's worth verifying that niri doesn't expect `"FocusColumnLeft"` (unit form) for empty structs. Based on the wire format tests, this appears intentional and correct.

*Severity: Very Low / Verified OK*

**T-6: `gen_all_unit_str_enum_code` has dead code**
`generate_types.py:175`: The first two lines create an unused `StrEnum` class that's immediately overwritten by line 177. This is a dead code artifact.

*Severity: Very Low / Cleanup*

---

## 3. Transport Layer

### Strengths

- **Clean error mapping**: `TimeoutError` → `NiriTimeoutError`, `OSError` → `TransportError`, `LimitOverrunError` → `ProtocolError`. Every asyncio exception is mapped to a domain-specific error.
- **Idempotent `close()`** — safe to call multiple times.
- **`_closed` flag prevents use-after-close** on both read and write paths.
- **`max_frame_size` double-checked** — both via `readuntil` limits and explicit post-read size check.

### Concerns

**TR-1: `LimitOverrunError` uses `max_size` parameter in error message but the actual limit is `stream_limit`**
`connection.py:132-136`: When `LimitOverrunError` fires, the error message says "Frame exceeds maximum {max_size} bytes" — but the actual limit that triggered the error is `stream_limit` (set during connection), not `max_size` (the parameter to `read_frame`). These are typically the same (`max(max_frame_size + 1, DEFAULT_STREAM_LIMIT)`), but the error message could be misleading if they diverge.

*Severity: Low / Diagnostics*

**TR-2: `write_frame` doesn't enforce newline termination**
`write_frame(data: bytes)` writes raw bytes without ensuring a trailing `\n`. The caller (client.py:112) appends `+ b"\n"` manually. If a caller forgets the newline, the server will hang waiting for the delimiter. The framing guarantee should live in the transport layer, not the caller.

*Severity: Medium / API Design*
*Consider having `write_frame` automatically append `\n`, or renaming to `write_raw` to make the contract explicit.*

**TR-3: No write timeout**
`write_frame` calls `self._writer.drain()` without a timeout. If the socket buffer is full and the peer is slow to read, `drain()` can block indefinitely. This is unlikely in practice (niri's IPC is local and fast), but it's an asymmetry — reads have timeouts, writes don't.

*Severity: Low*

---

## 4. API Layer

### Strengths

- **Typed overloads on `NiriClient.request()`** — 15 overloads provide precise return types for each request type. This is excellent for IDE autocompletion and static analysis.
- **Reply.unwrap()** — clean Result-style unwrapping that converts `Err` replies to `RemoteError`.
- **Event stream backpressure** — two configurable modes (DROP_OLDEST, FAIL_FAST) with bounded queues.
- **Bootstrap handshake** — event stream validates the `Handled` response before entering the read loop.
- **Bundle close semantics** — propagates first error, doesn't mask subsequent errors.

### Concerns

**API-1: `NiriEventStream._enqueue_terminal` can silently fail**
`event_stream.py:106-119`: The terminal item enqueue has a double try/except that silently drops the terminal signal if the queue is completely stuck. This means a consumer calling `next()` could block forever waiting for a terminal item that was never enqueued.

*Severity: Medium*
*The `_terminal_cause` field provides a fallback path (checked in `next()` at line 203-210), but only if the lifecycle transitions to terminal state. If the lifecycle is stuck in `READY` and the terminal item is lost, `next()` will hang on `queue.get()` until its timeout (which may be `None`).*

**API-2: `NiriEventStream.__anext__` catches `LifecycleError` to raise `StopAsyncIteration`**
`event_stream.py:253-257`: This means that if the stream closes due to an error, `async for` silently stops rather than propagating the error. This is the standard Python async iterator convention, but it means errors are silently swallowed in `async for` loops. Users must check `.is_closed` or use `.next()` directly to observe errors.

*Severity: Low / Design Choice*
*This is a known trade-off. Consider documenting it prominently.*

**API-3: `NiriEventStream.connect()` creates the background reader task before transitioning to READY**
`event_stream.py:83-85`: The reader task is created at line 83, and the transition to READY happens at line 85. There's a brief window where the task is running but the lifecycle is in CONNECTING state. If the reader immediately encounters an error, it calls `_close_reader_resources()` which tries to transition to CLOSING — but from CONNECTING, that transition is invalid (only CONNECTING → READY or CONNECTING → CLOSED are valid). The code handles this with `except LifecycleError: return` at line 188, but it's a subtle race.

*Severity: Low / Robustness*

**API-4: `NiriConnectionBundle.open()` catches all exceptions during event stream connect**
`bundle.py:31-34`: `except Exception:` is broad. It would also catch `KeyboardInterrupt` (which is a `BaseException`, not caught) and `SystemExit` (also `BaseException`, not caught), which is fine. But it catches things like `TypeError` or `AttributeError` from programming errors, which would be masked as connection failures.

*Severity: Very Low*

**API-5: `NiriClient` doesn't expose the `actions` module in its API**
Users must import from `niri_pypc.actions` separately and then pass the result to `client.request()`. This is fine architecturally (separation of concerns), but the discoverability could be improved. The `__init__.py` imports `actions` as a module (`import niri_pypc.actions`), making it accessible as `niri_pypc.actions.spawn(...)`, which is good.

*Severity: Very Low / Ergonomics*

---

## 5. Action Builder Module

### Strengths

- **100% test coverage** — every builder and helper is tested.
- **Complete coverage** — 137 builders cover all non-debug action variants; a meta-test enforces this.
- **Ergonomic workspace coercion** — `int` → Id, `str` → Name, `WorkspaceReferenceArg` → pass-through.
- **Clean `_wrap()` helper** — single indirection point from variant to `ActionRequest`.
- **Sensible defaults** — `quit(skip_confirmation=False)`, `move_window_to_workspace(focus=True)`, `screenshot(show_pointer=False)`.
- **Wire format tests** — verify that builder output serializes to the exact JSON niri expects.
- **`__all__` completeness test** — ensures exports stay in sync.

### Concerns

**ACT-1: Import sorting violation (ruff I001)**
`actions.py` has an import sorting violation: the `from niri_pypc.types.generated.action import (...)` block uses semantic comments (`# -- Tier 1 --`, `# -- Tier 2 --`) that break ruff's import sorting. Auto-fixing with `ruff --fix` would strip the comments and reorder.

*Severity: Low / Style*
*Either add `# noqa: I001` or restructure the imports to satisfy ruff. The semantic comments are informative but conflict with tooling.*

**ACT-2: `actions.quit()` shadows the built-in `quit`**
The function name `quit` shadows Python's built-in `quit()`. While unlikely to cause issues in practice (no one calls `quit()` in async code), it could confuse linters and IDEs.

*Severity: Very Low / Naming*
*Could be `quit_niri()` or left as-is since it's namespaced under `niri_pypc.actions`.*

**ACT-3: Several builder parameters shadow built-in `id`**
Functions like `focus_window(id: int)`, `close_window(id: int | None = None)` shadow the built-in `id()`. This is a common Python pattern and not a practical issue, but it's worth noting for completeness.

*Severity: Very Low / Unavoidable*
*The parameter names match the niri IPC protocol field names, so changing them would break the mapping.*

**ACT-4: No runtime validation on builder inputs**
The builders pass arguments directly to Pydantic model constructors, which perform validation. This is correct and efficient. However, the error messages from Pydantic validation failures may be confusing to users unfamiliar with the generated types. For example, passing a float to `focus_column(index=1.5)` would produce a Pydantic validation error mentioning `FocusColumnAction.index` rather than `focus_column(index=...)`.

*Severity: Low / Ergonomics*

**ACT-5: Debug actions intentionally excluded but no documentation why**
The `SKIP_DEBUG` set in tests (`DebugToggleDamage`, `DebugToggleOpaqueRegions`, `ToggleDebugTint`) implies these are intentionally omitted from the builder module, but there's no comment or documentation explaining the decision.

*Severity: Very Low / Documentation*

---

## 6. Error Handling

### Strengths

- **Rich error hierarchy** — 9 exception classes with contextual metadata (`operation`, `socket_path`, `retryable`, `cause`).
- **`retryable` flag** — allows callers to implement retry logic without parsing error messages.
- **`raw_payload` truncation** — `DecodeError` truncates raw payloads to 1024 chars, preventing log/memory bloat.
- **Multiple inheritance** — `NiriTimeoutError(NiriError, TimeoutError)` allows catching either.
- **Error chain preservation** — `from exc` used consistently for exception chaining.

### Concerns

**E-1: `DecodeError.__init__` uses `**kwargs: Any` pass-through**
`errors.py:46`: `**kwargs: Any` is passed to `super().__init__()`. This means `DecodeError` accepts any keyword argument that `NiriError.__init__` accepts, but the type signature doesn't document this. Using explicit parameters would be clearer.

*Severity: Very Low / Type Safety*

**E-2: `NiriError.cause` duplicates Python's built-in `__cause__`**
The `cause` field on `NiriError` stores the original exception, but Python's `raise X from Y` already sets `X.__cause__ = Y`. This is redundant but not harmful — it provides explicit access without requiring knowledge of Python's exception chaining semantics.

*Severity: Very Low / Design Choice*

---

## 7. Test Suite

### Strengths

- **96% line coverage** — excellent for a library of this size.
- **100% coverage on actions, config, lifecycle, generated types** — the most critical modules are fully covered.
- **Multi-layer testing**: codec contract tests, generated type shape tests, API integration tests, wire format roundtrips.
- **Forward compatibility testing** — unknown variant handling verified.
- **Completeness meta-tests** — `test_all_non_debug_actions_have_builders()` and `test_all_exports_match()` prevent drift.
- **Nested niri harness** — sophisticated e2e test infrastructure with headless/visible modes, scenario fixtures, failure artifact capture.
- **Async testing discipline** — `asyncio_mode = "auto"` with proper mock socket servers.

### Coverage Gaps

**TEST-1: `NiriEventStream` has 80% coverage (38 uncovered lines)**
Key uncovered paths:
- `_enqueue_terminal` double-retry logic (lines 114-119)
- Decode error in reader loop (lines 142-151)
- FAIL_FAST backpressure mode (lines 161-174)
- General exception handler in reader (lines 176-178)
- Reader resource cleanup edge cases (lines 184, 195, 199-200)
- `__anext__` / `StopAsyncIteration` path (lines 254-257)

*Severity: Medium — these are important error paths that should be tested.*

**TEST-2: `NiriConnectionBundle` has 79% coverage**
Uncovered: event stream connect failure cleanup (line 32-34), close error propagation (lines 55-64).

*Severity: Medium — cleanup on partial failure is critical for resource safety.*

**TEST-3: No tests for FAIL_FAST backpressure mode**
The `BackpressureMode.FAIL_FAST` path in the event stream reader (lines 165-174) is completely untested.

*Severity: Medium*

**TEST-4: No tests for malformed JSON from server**
If niri sends invalid JSON, the event stream reader should catch the decode error and terminate gracefully. This path (lines 140-151) is untested.

*Severity: Low-Medium*

**TEST-5: No tests for `NiriClient` connection failure**
`NiriClient.request()` → `UnixConnection.connect()` failure (socket not found, permission denied, etc.) is indirectly tested via transport tests but not tested at the client API level.

*Severity: Low*

**TEST-6: Integration tests require niri binary**
The nested niri integration tests skip if `niri` is not available. This is appropriate, but it means CI may not exercise the most valuable tests. Consider documenting the CI setup required for full coverage.

*Severity: Low / CI*

---

## 8. Code Quality & Style

### Strengths

- **Consistent formatting** — ruff configured with sensible rules (E/F/I/UP/B).
- **Generated code excluded** from formatting/linting — appropriate since it's machine-produced.
- **`from __future__ import annotations`** used consistently for PEP 604 syntax.
- **Minimal dependencies** — only `pydantic>=2.12.5` at runtime.
- **PEP 561 compliant** — `py.typed` marker included.
- **Good docstrings** on public-facing functions and classes.

### Concerns

**Q-1: Single ruff violation in `actions.py` (I001: unsorted imports)**
The import block uses semantic comments that conflict with ruff's import sorter. This should be resolved.

*Severity: Low*

**Q-2: `types/__init__.py` uses `from ... import *` (star import)**
`types/__init__.py:11`: `from niri_pypc.types.generated import *` re-exports everything. This is convenient but makes it hard to audit what's actually exported. The `__all__` in the generated `__init__.py` controls this, so it's manageable.

*Severity: Very Low*

**Q-3: Unused import `Any` in `client.py`**
`client.py:5`: `from typing import Any, overload` — `Any` appears unused (it's only used in `__aexit__` parameter which is `*exc: Any`). Actually, `*exc: Any` does use it. This is fine.

*Severity: None — false alarm*

**Q-4: `generate_types.py` generates StrEnum import but doesn't use `from enum import StrEnum`**
The generated `models.py` has `from enum import StrEnum` at the top. The generator (`gen_all_unit_str_enum_code`) references `StrEnum` as a base class. This is correct for Python 3.11+. Since the project requires Python 3.13+, this is fine.

*Severity: None*

---

## 9. Security Considerations

**S-1: No input sanitization on `SpawnAction` / `SpawnShAction`**
`actions.spawn(command: list[str])` and `actions.spawn_sh(command: str)` construct process-spawn requests that niri executes. The library correctly passes these through without modification — sanitization is niri's responsibility. However, the `spawn_sh` builder accepts arbitrary shell commands. Users should be warned about command injection risks if the shell command includes user-controlled input.

*Severity: Low / Documentation*
*Consider adding a docstring note about command injection risks on `spawn_sh()`.*

**S-2: `max_frame_size` default is 4 MiB**
The default `max_frame_size` of 4 MiB is reasonable for IPC. A malicious or buggy compositor could send up to 4 MiB before the client rejects the frame, which is acceptable for local IPC.

*Severity: None — appropriate default*

**S-3: Unix socket path from environment variable**
`NiriConfig.resolve_socket_path()` reads `NIRI_SOCKET` from the environment. This is the standard niri convention and is safe for IPC clients.

*Severity: None*

---

## 10. Findings Summary

### By Severity

| Severity | Count | IDs |
|----------|-------|-----|
| Medium   | 5     | T-4, TR-2, API-1, TEST-1, TEST-2/3 |
| Low      | 12    | A-1, A-2, T-3, TR-1, TR-3, API-2, API-3, ACT-1, ACT-4, E-1, TEST-4/5, S-1 |
| Very Low | 10    | T-1, T-2, T-5, T-6, API-4, API-5, ACT-2, ACT-3, ACT-5, E-2, Q-1, Q-2 |

### By Category

| Category | Findings |
|----------|----------|
| Architecture | 2 (A-1, A-2) |
| Type System | 6 (T-1 through T-6) |
| Transport | 3 (TR-1, TR-2, TR-3) |
| API | 5 (API-1 through API-5) |
| Actions | 5 (ACT-1 through ACT-5) |
| Errors | 2 (E-1, E-2) |
| Tests | 6 (TEST-1 through TEST-6) |
| Code Quality | 2 (Q-1, Q-2) |
| Security | 1 (S-1) |

---

## 11. Recommendations

### Priority 1 — Should Fix

1. **TR-2: Add newline framing to `write_frame`** — Move the `+ b"\n"` from callers into `write_frame()` to make the NDJSON framing guarantee a transport-layer invariant.

2. **TEST-1/2/3: Improve event stream and bundle test coverage** — Add tests for:
   - FAIL_FAST backpressure mode
   - Malformed JSON decode error in reader loop
   - Bundle partial-failure cleanup
   - `__anext__` → `StopAsyncIteration` path

3. **T-4: Consider preserving tuple types for fixed-length arrays** — The IR normalizer's heuristic of collapsing `[int, int]` → `list[int]` loses semantic information. Either:
   - Use `tuple[int, int]` for homogeneous fixed-length arrays, or
   - Add a Pydantic field validator for length checking, or
   - Document the limitation

### Priority 2 — Nice to Have

4. **ACT-1: Fix ruff I001 violation** — Either reorder imports or add a `# noqa: I001` suppression.

5. **API-1: Harden terminal item enqueue** — The double try/except in `_enqueue_terminal` is fragile. Consider using a dedicated `asyncio.Event` for terminal signaling alongside the queue.

6. **A-2: Rename `NiriClient.connect()` to `NiriClient.create()`** — More accurately describes the method's behavior (validation only, no connection).

7. **S-1: Add command injection warning to `spawn_sh()` docstring**.

### Priority 3 — Optional

8. **T-6: Remove dead code in `gen_all_unit_str_enum_code`** — Delete the overwritten initial `StrEnum` class.

9. **ACT-5: Document why debug actions are excluded from builders** — A brief comment in the actions module or a note in `__all__`.

10. **TEST-6: Document CI requirements for integration tests** — Ensure the README or CI config explains how to run nested niri tests.

---

## Appendix: Files Reviewed

| File | Lines | Status |
|------|-------|--------|
| `src/niri_pypc/__init__.py` | 44 | Reviewed |
| `src/niri_pypc/actions.py` | 1,160 | Reviewed |
| `src/niri_pypc/config.py` | 43 | Reviewed |
| `src/niri_pypc/errors.py` | 94 | Reviewed |
| `src/niri_pypc/api/client.py` | 135 | Reviewed |
| `src/niri_pypc/api/event_stream.py` | 286 | Reviewed |
| `src/niri_pypc/api/bundle.py` | 70 | Reviewed |
| `src/niri_pypc/transport/connection.py` | 178 | Reviewed |
| `src/niri_pypc/runtime/lifecycle.py` | 91 | Reviewed |
| `src/niri_pypc/types/base.py` | 99 | Reviewed |
| `src/niri_pypc/types/codec.py` | 141 | Reviewed |
| `src/niri_pypc/types/__init__.py` | 11 | Reviewed |
| `src/niri_pypc/types/generated/models.py` | 393 | Reviewed |
| `src/niri_pypc/types/generated/request.py` | 114 | Reviewed |
| `src/niri_pypc/types/generated/reply.py` | 141 | Reviewed |
| `src/niri_pypc/types/generated/event.py` | 126 | Reviewed |
| `src/niri_pypc/types/generated/action.py` | 880 | Reviewed |
| `src/niri_pypc/types/generated/_metadata.py` | 16 | Reviewed |
| `tools/generate_types.py` | 462 | Reviewed |
| `tools/normalize_ir.py` | 407 | Reviewed |
| `tests/test_actions.py` | 559 | Reviewed |
| `tests/conftest.py` | 295 | Reviewed |
| All other test files | ~2,500 | Reviewed (via agent) |
| `pyproject.toml` | 108 | Reviewed |
| **Total** | **~7,500** | |

---

*End of review.*
