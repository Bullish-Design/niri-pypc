# ACTION_REFACTOR_CODE_REVIEW_REFACTOR_GUIDE

## Table of Contents

1. Objective and Working Rules
   - What to implement, strict constraints, and quality gates.
2. Codebase Map for This Refactor
   - Exact modules/tests/docs touched by each review item.
3. Implementation Order (Do Not Reorder)
   - Safe sequence to reduce regressions and merge conflicts.
4. Phase 0: Branch Setup and Baseline Verification
   - Required startup commands and baseline checks.
5. Phase 1: Transport Framing Invariant and Timeout Hardening
   - TR-2, TR-4, optional TR-3 implementation details.
6. Phase 2: Event Stream Robustness and Lifecycle Race Fixes
   - API-1, API-3, API-2 iterator unification.
7. Phase 3: API Naming and Compatibility Transition
   - A-2 (`connect()` -> `create()` with alias period).
8. Phase 4: Bundle and Client Failure-Path Coverage Expansion
   - TEST-1/2/3/4/5 additions with deterministic fixtures.
9. Phase 5: Type/Schema Fidelity and Generator Updates
   - T-4, T-3, T-6, optional T-1, regeneration flow.
10. Phase 6: Actions Module Lint and Safety Documentation
    - ACT-1, ACT-5, S-1 cleanup and rationale docs.
11. Phase 7: Documentation + Integration Prerequisites
    - API behavior notes and TEST-6 docs.
12. Phase 8: Final Validation and PR Assembly
    - Full quality gate, commit slicing, and review checklist.
13. Detailed File-by-File Change Matrix
    - Item -> file/function/test mapping.
14. Intern Execution Checklist
    - One-pass operational checklist.

## 1. Objective and Working Rules

This guide translates `.scratch/projects/11-action-refactor-review/ACTION_REFACTOR_CODE_REVIEW_REFACTOR.md` into an implementation script an intern can execute directly.

Non-negotiable repo rules while implementing:
- Use `devenv shell -- ...` for all environment-dependent commands.
- Before first test run of this session: `devenv shell -- uv sync --extra dev`.
- Default test suite command: `devenv shell -- pytest -m "not visible_demo and not smoke"`.
- Do not run visible nested tests unless explicitly requested by maintainer.
- For every Python edit run:
  1. `devenv shell -- ruff check .`
  2. `devenv shell -- ruff format --check .`
  3. `devenv shell -- ty check .` (when signatures/public interfaces/type models change)

## 2. Codebase Map for This Refactor

Core implementation modules:
- `src/niri_pypc/transport/connection.py`
- `src/niri_pypc/api/client.py`
- `src/niri_pypc/api/event_stream.py`
- `src/niri_pypc/api/bundle.py`
- `src/niri_pypc/types/base.py`
- `src/niri_pypc/actions.py`
- `tools/normalize_ir.py`
- `tools/generate_types.py`

Primary tests to update/add:
- `tests/transport/test_connection.py`
- `tests/api/test_event_stream.py`
- `tests/api/test_client.py`
- `tests/api/test_bundle.py`
- `tests/types/test_generated_shapes.py`
- `tests/types/test_roundtrip.py`
- `tests/types/test_reply_roundtrip.py`
- `tests/test_actions.py`

Docs likely touched:
- `README.md`
- optional changelog/release notes file if present

Generated outputs (regenerated, not hand-edited):
- `src/niri_pypc/types/generated/models.py`
- `src/niri_pypc/types/generated/request.py`
- `src/niri_pypc/types/generated/reply.py`
- `src/niri_pypc/types/generated/event.py`
- `src/niri_pypc/types/generated/action.py`
- `src/niri_pypc/types/generated/_metadata.py`

## 3. Implementation Order (Do Not Reorder)

1. Transport framing invariant first (removes duplicated newline logic at call sites).
2. Event stream terminal/lifecycle hardening second (depends on stable transport behavior).
3. API naming transition third (`connect`/`create`) to avoid churn during earlier refactors.
4. Expand tests for bundle/client/event error paths.
5. Type schema fidelity/codegen updates and regeneration.
6. Actions lint/docs cleanup.
7. Final docs + validation + PR assembly.

## 4. Phase 0: Branch Setup and Baseline Verification

1. Create a branch for the refactor.
2. Sync dependencies:
   - `devenv shell -- uv sync --extra dev`
3. Establish baseline quality:
   - `devenv shell -- ruff check .`
   - `devenv shell -- ruff format --check .`
   - `devenv shell -- pytest -m "not visible_demo and not smoke"`
4. Save baseline failures (if any) in project notes before making edits.

## 5. Phase 1: Transport Framing Invariant and Timeout Hardening

### 5.1 TR-2: Centralize newline framing in `UnixConnection.write_frame`

Files:
- `src/niri_pypc/transport/connection.py`
- `src/niri_pypc/api/client.py`
- `src/niri_pypc/api/event_stream.py`
- tests in `tests/transport/test_connection.py`, `tests/api/test_client.py`, `tests/api/test_event_stream.py`

Steps:
1. In `UnixConnection.write_frame`, normalize outbound payload:
   - if `data.endswith(b"\n")`: write as-is
   - else append newline once.
2. Keep method idempotent (never produce double newline).
3. In `NiriClient.request`, remove explicit `+ b"\n"` from `outbound` build.
4. In `NiriEventStream._bootstrap`, remove explicit `+ b"\n"` from `outbound` build.
5. Add tests:
   - connection writes newline when missing.
   - connection preserves single newline when present.
   - client request server still receives exactly one trailing newline.
   - event stream bootstrap request still newline terminated once.

### 5.2 TR-4: Poison connection on read timeout

File:
- `src/niri_pypc/transport/connection.py`

Steps:
1. In `read_frame`, on `TimeoutError`, set `self._closed = True` before raising `NiriTimeoutError`.
2. Add code comment documenting why (stream state after timeout is treated as indeterminate).
3. Add regression tests in `tests/transport/test_connection.py`:
   - induce read timeout
   - assert subsequent `read_frame` raises closed-connection `TransportError`
   - assert subsequent `write_frame` raises closed-connection `TransportError`

### 5.3 Optional TR-3: add write timeout symmetry

If accepted by maintainer:
1. Add optional `timeout` parameter to `write_frame` or use config-level write timeout.
2. Wrap `drain()` with `asyncio.wait_for`.
3. Map timeout to `NiriTimeoutError(operation="write_frame")`.
4. Add transport tests for timed-out writes using controlled server stall.

## 6. Phase 2: Event Stream Robustness and Lifecycle Race Fixes

### 6.1 API-1: terminal signaling independent from queue pressure

File:
- `src/niri_pypc/api/event_stream.py`

Implementation pattern:
1. Add `self._terminal_event = asyncio.Event()` in constructor.
2. Add helper to atomically set terminal cause and event.
3. In all terminal paths in `_run_reader`, set cause + terminal event before exit.
4. Keep queue terminal items for compatibility, but do not rely on queue insert for liveness.
5. In `next()`:
   - before waiting on queue, if terminal event is set and queue empty: raise terminal cause or closed lifecycle error immediately.
   - after timeout, still raise `NiriTimeoutError`.
6. Ensure `close()` sets terminal event as well.

Tests (`tests/api/test_event_stream.py`):
- saturated queue does not cause infinite wait on terminal.
- terminal cause remains observable even if `_enqueue_terminal` cannot enqueue immediately.

### 6.2 API-3: eliminate connect/reader lifecycle race

Current risk:
- reader task may run/exit before lifecycle is in `READY`, then close path hits transition ordering edge.

Steps:
1. Choose one path and apply consistently:
   - preferred: transition `CONNECTING -> READY` before creating reader task; or
   - preserve order but explicitly allow/connect failure path without invalid transition.
2. Ensure `_close_reader_resources` handles state defensively without dropping cleanup.
3. Add fast-failure connect race test (force immediate server close right after bootstrap).

### 6.3 API-2: async iterator architecture unification

File:
- `src/niri_pypc/api/event_stream.py`

Steps:
1. Change `__aiter__` to return `self`.
2. Remove/deprecate `_async_iterator` path to avoid dual semantics.
3. Keep one logic path through `__anext__`.
4. In `__anext__`:
   - convert terminal/closed lifecycle to `StopAsyncIteration`
   - re-raise non-terminal unexpected lifecycle/internal faults.
5. Update docstrings to describe difference between:
   - `next()` for explicit error handling
   - `async for` for stream consumption semantics.

Tests:
- `async for` stops on normal close.
- malformed event decode surfaces as failure when using direct `next()`.
- iterator path behavior is deterministic and not swallowing unexpected faults.

## 7. Phase 3: API Naming and Compatibility Transition

### 7.1 A-2: `NiriClient.connect()` -> `NiriClient.create()`

Files:
- `src/niri_pypc/api/client.py`
- `src/niri_pypc/api/bundle.py`
- all usage/docs/tests that currently call `NiriClient.connect(...)`

Steps:
1. Add classmethod `create(config: NiriConfig | None = None) -> NiriClient` with current behavior.
2. Keep `connect` as compatibility alias for one release:
   - either method wrapper calling `create`
   - include deprecation note in docstring.
3. Update internal call sites to use `create` (`bundle.py`, helpers/tests/docs).
4. Add compatibility test in `tests/api/test_client.py` proving both constructors behave identically.
5. Update README usage snippets to prefer `NiriClient.create`.

## 8. Phase 4: Bundle and Client Failure-Path Coverage Expansion

### 8.1 Event stream failure-path coverage (TEST-1/2/3/4)

In `tests/api/test_event_stream.py`, add cases for:
1. FAIL_FAST backpressure:
   - tiny queue capacity
   - burst events
   - assert `ProtocolError("Event queue full (FAIL_FAST mode)")`.
2. malformed JSON event frame:
   - server sends invalid JSON after successful bootstrap
   - assert `DecodeError` surfaced.
3. terminal enqueue pressure robustness:
   - force full queue at terminal and ensure consumer still gets terminal outcome.
4. explicit `__anext__` close path:
   - close stream then call `anext(stream)` and assert `StopAsyncIteration`.

### 8.2 Bundle lifecycle coverage (TEST-5)

In `tests/api/test_bundle.py`, add:
1. open partial failure:
   - make event stream connect fail
   - assert `client.close()` called (resource cleanup).
2. close error propagation order:
   - client close fails, events close fails
   - assert first error policy is preserved.

### 8.3 Client API boundary failure mapping

In `tests/api/test_client.py`, add:
1. force `UnixConnection.connect` failure path from `request()`.
2. assert raised domain error class/message includes operation context.

## 9. Phase 5: Type/Schema Fidelity and Generator Updates

### 9.1 T-4 decision gate (must be recorded)

Before code changes, record chosen strategy in `.scratch/projects/11-action-refactor-review/DECISIONS.md`:
- Preferred: always represent fixed-length `prefixItems` as tuple types.

### 9.2 Implement tuple fidelity in IR normalizer

File:
- `tools/normalize_ir.py`

Steps:
1. Update `_normalize_prefix_items` to always emit `tuple<...>` for non-empty fixed-length arrays, including homogeneous arrays.
2. Keep empty prefix fallback deterministic (`array<ref:Unknown>` acceptable).
3. Update function docstring to match behavior.

### 9.3 Regenerate types

Commands:
1. `devenv shell -- normalize-ir`
2. `devenv shell -- generate-types`
3. `devenv shell -- verify-generated`

### 9.4 Update tests for tuple fields

Files likely impacted:
- `tests/types/test_generated_shapes.py`
- `tests/types/test_reply_roundtrip.py`
- any tests referencing `physical_size` as list.

Add checks that fixed-length fields are tuple typed and length-constrained via pydantic validation.

### 9.5 T-3: serializer invariant guard for newtype payloads

File:
- `src/niri_pypc/types/base.py`

Steps:
1. In `ExternallyTaggedEnum._encode_root`, harden `kind == "newtype"` branch:
   - validate payload attribute exists and is serializable.
   - raise explicit `TypeError`/`EncodeError` with actionable message on invariant violation.
2. Add focused runtime tests in `tests/types/test_base_runtime.py` (or closest existing file).

### 9.6 T-6: remove dead assignment in codegen

File:
- `tools/generate_types.py`

Steps:
1. In `gen_all_unit_str_enum_code`, remove overwritten initial `lines` assignment.
2. Verify generated output stays unchanged apart from intended diffs.

### 9.7 Optional T-1: cache intent clarity

File:
- `src/niri_pypc/types/base.py`

Action:
- keep `@cache` or replace with `@lru_cache(maxsize=None)` and document rationale inline.

## 10. Phase 6: Actions Module Lint and Safety Documentation

### 10.1 ACT-1: resolve import sorting

File:
- `src/niri_pypc/actions.py`

Steps:
1. Prefer ruff-compliant import ordering with short comments for grouping intent.
2. If grouping must stay exact, use local `# noqa: I001` with rationale directly above import.
3. Ensure `ruff check .` passes without global ignores.

### 10.2 S-1: shell injection warning for `spawn_sh`

Files:
- `src/niri_pypc/actions.py`
- `README.md`

Steps:
1. Expand `spawn_sh` docstring with explicit warning:
   - do not pass untrusted input.
   - prefer `spawn([...])` for untrusted arguments.
2. Add same warning in README action usage section.

### 10.3 ACT-5: document debug-action exclusion rationale

Files:
- `src/niri_pypc/actions.py`
- `tests/test_actions.py`

Steps:
1. Add concise module comment explaining why debug-only actions are intentionally excluded from ergonomic builders.
2. Add matching note by relevant test constants/sections.

## 11. Phase 7: Documentation + Integration Prerequisites

### 11.1 Update README for API semantics

Required docs updates:
1. `NiriClient.create()` as canonical constructor, `connect()` deprecated alias.
2. Transport framing note should reflect that `write_frame()` enforces newline.
3. Event iterator behavior note (`next()` vs `async for`) after API-2 changes.
4. TEST-6: explicitly document integration/nested prerequisites and default non-visual test path.

## 12. Phase 8: Final Validation and PR Assembly

Run full gate in this order:
1. `devenv shell -- ruff check .`
2. `devenv shell -- ruff format --check .`
3. `devenv shell -- ty check .`
4. Targeted tests:
   - `devenv shell -- pytest tests/transport/test_connection.py -q`
   - `devenv shell -- pytest tests/api/test_event_stream.py tests/api/test_bundle.py tests/api/test_client.py -q`
   - `devenv shell -- pytest tests/types -q`
   - `devenv shell -- pytest tests/test_actions.py -q`
5. Full default suite:
   - `devenv shell -- pytest -m "not visible_demo and not smoke"`

Commit slicing (recommended):
1. transport framing + timeout poisoning + tests
2. event stream terminal/lifecycle refactor + tests
3. client naming transition + compatibility tests/docs
4. bundle/client/event coverage expansion
5. normalize IR + generated files + type tests
6. type base/runtime serializer guard + generator dead code cleanup
7. actions lint/docs + README/documentation updates

## 13. Detailed File-by-File Change Matrix

- `src/niri_pypc/transport/connection.py`
  - `write_frame`: newline invariant, optional write timeout.
  - `read_frame`: timeout poisons connection.
- `src/niri_pypc/api/client.py`
  - remove manual newline append in request payload.
  - add `create()` classmethod; keep `connect()` alias with deprecation note.
- `src/niri_pypc/api/event_stream.py`
  - remove manual newline append in bootstrap payload.
  - add terminal event primitive and atomic terminal signaling.
  - unify async iteration path and close semantics.
  - lifecycle race cleanup around READY/task creation.
- `src/niri_pypc/api/bundle.py`
  - migrate constructor use to `NiriClient.create()`.
  - retain partial-failure cleanup behavior with tests.
- `src/niri_pypc/types/base.py`
  - harden newtype serializer payload invariant.
  - clarify cache decoration intent.
- `tools/normalize_ir.py`
  - fixed-length `prefixItems` normalization to tuple fidelity.
- `tools/generate_types.py`
  - remove dead assignment in `gen_all_unit_str_enum_code`.
- `src/niri_pypc/actions.py`
  - import-sort/lint resolution.
  - shell safety warning in `spawn_sh` docs.
  - debug-action exclusion rationale comment.
- `README.md`
  - update client constructor usage + behavior notes + integration prerequisites.
- Tests listed in Sections 5-10
  - add deterministic failure-path and schema-shape coverage.

## 14. Intern Execution Checklist

1. Create branch and run baseline checks.
2. Implement transport framing invariant and timeout poisoning.
3. Update client/event stream call sites to stop manual newline appends.
4. Add/adjust transport tests for newline idempotency and post-timeout closed behavior.
5. Implement event terminal event signaling + lifecycle race fix.
6. Unify async iterator semantics and update event stream tests.
7. Introduce `NiriClient.create()`, keep `connect()` alias, migrate internal call sites and docs.
8. Add bundle/client/event failure-path tests from matrix.
9. Record T-4 strategy in `DECISIONS.md`.
10. Update `tools/normalize_ir.py`, regenerate types, and update tuple-related tests.
11. Harden newtype serializer path in `types/base.py` and add tests.
12. Remove dead generator assignment in `tools/generate_types.py`.
13. Resolve actions import lint and add `spawn_sh` safety docs.
14. Run full quality gate and required test sets.
15. Prepare PR with commit messages referencing review IDs (TR-2, API-1, T-4, etc.).
