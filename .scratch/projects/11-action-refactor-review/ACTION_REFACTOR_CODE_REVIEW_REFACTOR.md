# ACTION_REFACTOR_CODE_REVIEW_REFACTOR

## Table of Contents

1. Purpose and Scope
   - Defines what this guide covers and how to use it.
2. Current-State Snapshot
   - Captures confirmed behavior in the current codebase to ground each fix.
3. Refactor Strategy and Sequencing
   - Orders work to reduce risk and avoid churn.
4. Priority 1 Refactors (Should Fix)
   - Detailed implementation steps for correctness and robustness issues.
5. Priority 2 Refactors (Nice to Have)
   - Detailed implementation steps for API clarity, hardening, and ergonomics.
6. Priority 3 Refactors (Optional)
   - Cleanup/documentation improvements with lower impact.
7. Testing Matrix
   - Maps each refactor item to targeted tests and quality gates.
8. Rollout Plan
   - Branching, commit slicing, and merge order recommendations.
9. Acceptance Criteria
   - Concrete definition of done per category.
10. Risk Register and Mitigations
    - Main refactor risks and specific controls.
11. Execution Checklist
    - End-to-end actionable checklist for implementation.

## 1. Purpose and Scope

This document is the implementation playbook for refactoring all recommended fixes from `ACTION_REFACTOR_CODE_REVIEW.md` against the current repository state.

Use this guide to:
- Implement changes in a low-risk order.
- Keep behavior stable while improving diagnostics, API safety, and test coverage.
- Enforce explicit acceptance criteria and quality gates before merge.

Out of scope:
- New product features unrelated to the review.
- Breaking protocol changes to niri IPC wire format.

## 2. Current-State Snapshot

Confirmed in current code:
- Transport currently requires callers to append newline framing (`src/niri_pypc/api/client.py`, `src/niri_pypc/api/event_stream.py`), while `UnixConnection.write_frame()` writes raw bytes.
- `NiriEventStream` terminal signaling uses queue insertion best-effort retries and may drop terminal marker under sustained full-queue pressure.
- `NiriClient.connect()` validates socket path but does not open a persistent connection.
- IR normalization collapses homogeneous `prefixItems` arrays into `array<T>` in `tools/normalize_ir.py`.
- `actions.py` import block intentionally grouped by semantic tiers but violates ruff import sorting.
- `tools/generate_types.py` contains dead assignment in `gen_all_unit_str_enum_code`.

## 3. Refactor Strategy and Sequencing

Implement in this order to minimize cascading edits:

1. Transport framing invariant + diagnostics (`TR-2`, `TR-1`, optional `TR-3`).
2. Event stream hardening and race cleanup (`API-1`, `API-3`, `API-2 docs/tests`).
3. Test coverage expansion (`TEST-1`, `TEST-2`, `TEST-3`, `TEST-4`, `TEST-5`).
4. Schema fidelity decision + implementation (`T-4`).
5. API naming clarity (`A-2`) with compatibility shim.
6. Action module lint/docs (`ACT-1`, `ACT-5`, `S-1`, optional `ACT-2`).
7. Type/generator cleanup (`T-3`, `T-6`, optional `T-1`) including newtype payload serialization guardrails.
8. CI/docs hardening (`TEST-6`, `API-2 behavior note`).

Rule: keep each numbered item in a separate commit unless tightly coupled.

## 4. Priority 1 Refactors (Should Fix)

### 4.1 TR-2: Make newline framing a transport-layer invariant

Goal:
- Ensure every frame written through `UnixConnection` is newline-delimited by transport itself.

Files:
- `src/niri_pypc/transport/connection.py`
- `src/niri_pypc/api/client.py`
- `src/niri_pypc/api/event_stream.py`
- Transport/API tests touching write framing behavior.

Steps:
1. Update `UnixConnection.write_frame(data: bytes)` to append `b"\n"` if missing.
2. Keep method idempotent for already-delimited payloads (do not duplicate newline).
3. Remove explicit `+ b"\n"` concatenation from client/event-stream call sites.
4. Add or update tests proving:
   - Caller without newline still sends valid frame.
   - Caller with newline does not get double delimiter.

Acceptance:
- No caller manually appends newline for normal request/event bootstrap writes.
- Frame protocol still passes existing roundtrip/integration tests.

### 4.2 TEST-1/2/3/4/5: Expand critical error-path and lifecycle tests

Goal:
- Close major coverage gaps in event stream and bundle lifecycle/error handling.

Primary files:
- `tests/api/test_event_stream.py`
- `tests/api/test_bundle.py`
- `tests/api/test_client.py`

Add tests for:
1. FAIL_FAST backpressure mode:
   - Fill queue to capacity.
   - Trigger additional event.
   - Assert `ProtocolError("Event queue full (FAIL_FAST mode)")` path and terminal behavior.
2. Malformed JSON from server:
   - Feed invalid JSON frame in stream.
   - Assert `DecodeError` captured/propagated on next consumption.
3. `_enqueue_terminal` robustness:
   - Simulate full queue and verify terminal signal remains observable (or enforced by new signaling mechanism).
4. `__anext__` StopAsyncIteration path:
   - Closed stream in `async for` terminates cleanly.
5. Bundle partial-failure cleanup:
   - Event stream connect fails.
   - Assert client close is invoked and resources are not leaked.
6. Bundle close error propagation:
   - Inject close failure on client/events and assert first error policy.
7. Client connection failure at API boundary:
   - Force `UnixConnection.connect` failure from `NiriClient.request` path.
   - Assert mapped domain exception behavior.

Acceptance:
- Coverage materially improves for `event_stream.py` and `bundle.py` error paths.
- All new tests deterministic and isolated (no real niri dependency unless explicitly integration-scoped).

### 4.3 API-1: Harden terminal signaling in event stream

Goal:
- Eliminate risk of consumers blocking forever due to dropped queue terminal markers.

Files:
- `src/niri_pypc/api/event_stream.py`
- `tests/api/test_event_stream.py`

Recommended design:
1. Add dedicated terminal signal primitive (`asyncio.Event`) to represent terminal state independently of queue capacity.
2. Set terminal cause + event atomically when reader exits on error.
3. In `next()`, before waiting on queue:
   - If terminal event set and queue empty, raise terminal cause (or closed lifecycle error).
4. Retain queue-based `_ErrorItem`/`_ClosedItem` for backward behavior where useful, but do not rely solely on queue insertion for liveness.

Acceptance:
- No infinite wait when terminal occurs with saturated queue.
- Existing queue semantics remain backward-compatible for normal consumers.

### 4.4 T-4: Restore fixed-length semantic fidelity for homogeneous `prefixItems`

Goal:
- Preserve tuple semantics (or enforce equivalent length validation) for fixed-length arrays currently widened to list.

Decision gate (pick one approach and document in `DECISIONS.md`):
1. Preferred: emit `tuple<T,T,...>` for any fixed-length `prefixItems`, even homogeneous.
2. Alternative: keep `list<T>` and add generated validators enforcing exact length.
3. Minimum: keep existing behavior but explicitly document schema-fidelity limitation.

Files:
- `tools/normalize_ir.py`
- `tools/generate_types.py` (if validator strategy chosen)
- regenerated `src/niri_pypc/types/generated/*.py`
- type and roundtrip tests in `tests/types/*`

Steps (tuple strategy):
1. Change `_normalize_prefix_items` to always output tuple form for fixed-length arrays.
2. Regenerate models.
3. Update affected tests for fields like `physical_size`/layout coordinate arrays.
4. Validate decode/encode compatibility with fixture payloads.

Acceptance:
- Python type signatures encode fixed-length constraint.
- Tests verify invalid lengths fail validation.

## 5. Priority 2 Refactors (Nice to Have)

### 5.1 ACT-1: Resolve `ruff` import sort violation in `actions.py`

Options:
1. Preferred: split semantically-grouped imports into ruff-compliant structure while preserving readability with nearby comments.
2. Alternative: targeted `# noqa: I001` on import block with rationale comment.

Acceptance:
- `devenv shell -- ruff check .` passes cleanly.

### 5.2 A-2: Rename `NiriClient.connect()` to `NiriClient.create()`

Goal:
- Align name with behavior (validation/factory only, no persistent socket connect).

Files:
- `src/niri_pypc/api/client.py`
- call sites (`bundle.py`, docs/tests)

Steps:
1. Add `create()` classmethod with current behavior.
2. Keep `connect()` as compatibility alias for one release with deprecation note in docstring.
3. Switch internal uses to `create()`.
4. Add test ensuring both names behave identically during transition.
5. Document deprecation in README/changelog.

Acceptance:
- No breaking change immediately.
- New canonical API name is discoverable.

### 5.3 API-3: Remove connect-to-reader race window

Goal:
- Ensure reader task starts only after lifecycle reaches `READY`, or lifecycle transitions allow the observed ordering.

Implementation options:
1. Move `transition_to(READY)` before task creation and guard task startup path.
2. Keep ordering but adjust lifecycle transitions in close path to safely handle CONNECTING failures.

Acceptance:
- No invalid transition exceptions in fast-failure connect race tests.

### 5.4 API-2: Normalize async-iterator architecture and document behavior

Goal:
- Eliminate split iterator behavior and make stream iteration semantics explicit.

Files:
- `src/niri_pypc/api/event_stream.py` docstrings
- `README.md` usage docs

Implementation decision:
1. Make `NiriEventStream` a true async iterator:
   - `__aiter__` returns `self`.
   - `__anext__` is the single iterator execution path.
2. Remove or deprecate `_async_iterator()` wrapper to avoid dual semantics.
3. In `__anext__`, convert to `StopAsyncIteration` only for terminal/closed conditions.
4. Re-raise non-terminal/non-close lifecycle faults instead of silently swallowing.
5. Add tests asserting `async for` stops on close but surfaces unexpected lifecycle faults.

Acceptance:
- Iterator control flow is consistent and testable through one code path.
- Users understand to call `.next()` when they want direct error propagation semantics.

### 5.5 TR-3: Add optional write timeout symmetry

Goal:
- Prevent unbounded `drain()` waits in pathological local IPC conditions.

Files:
- `src/niri_pypc/transport/connection.py`
- config/tests if exposing timeout knob

Acceptance:
- Write path can time out and map to `NiriTimeoutError` consistently.

### 5.6 TR-4: Poison connection on read timeout

Goal:
- Treat read timeout as a terminal connection fault for this connection instance.

Files:
- `src/niri_pypc/transport/connection.py`
- `tests/transport/test_connection.py`

Steps:
1. In `read_frame()`, set `self._closed = True` before raising `NiriTimeoutError` on timeout.
2. Add regression test:
   - induce read timeout;
   - verify subsequent read/write attempts raise closed-connection `TransportError`.
3. Document rationale in code comment: timeout leaves connection state indeterminate.

Acceptance:
- Timeout path transitions connection to unusable/closed state deterministically.

### 5.7 S-1: Add shell-injection warning to `spawn_sh()` docs

Goal:
- Warn users not to pass untrusted strings to shell builder.

Files:
- `src/niri_pypc/actions.py`
- `README.md` action examples

Acceptance:
- Warning appears in both code docstring and top-level docs.

## 6. Priority 3 Refactors (Optional)

### 6.1 T-6: Remove dead assignment in `gen_all_unit_str_enum_code`

File:
- `tools/generate_types.py`

Steps:
1. Remove the overwritten initial `lines` assignment.
2. Keep generated output unchanged.
3. Add small generator unit test or snapshot check if appropriate.

### 6.2 ACT-5: Document debug-action exclusion rationale

Files:
- `src/niri_pypc/actions.py` (module comment)
- `tests/test_actions.py` (adjacent to `SKIP_DEBUG`)

Goal:
- Explain why debug-only variants are excluded from ergonomic public builders.

### 6.3 T-3: Newtype payload invariant guard in serializer

File:
- `src/niri_pypc/types/base.py`

Steps:
1. Replace direct `root.payload` access with explicit guard.
2. Ensure payload serialization path is explicit and JSON-safe for nested protocol models (do not rely on accidental encoder behavior).
3. Raise `EncodeError`/`TypeError` with clear message when invariant or serialization assumptions are violated.

### 6.4 T-1: Clarify cache intent

File:
- `src/niri_pypc/types/base.py`

Action:
- Keep `@cache` or swap to `@lru_cache(maxsize=None)` with comment; pick one and record rationale.

### 6.5 TEST-6: Document integration-test prerequisites

File:
- `README.md` and/or contributing docs

Goal:
- Explain requirements for nested niri integration coverage in CI/local.

## 7. Testing Matrix

For every Python change, run:
1. `devenv shell -- ruff check .`
2. `devenv shell -- ruff format --check .`
3. `devenv shell -- ty check .` (required when signatures/public types/interfaces change)
4. Targeted tests for changed modules.
5. Full suite for cross-cutting changes.

Suggested targeted runs by workstream:
- Transport: `devenv shell -- pytest tests/transport/test_connection.py -q`
- Event stream + bundle + client API: `devenv shell -- pytest tests/api/test_event_stream.py tests/api/test_bundle.py tests/api/test_client.py -q`
- Types/codegen: `devenv shell -- pytest tests/types -q`
- Actions docs/lint changes: `devenv shell -- pytest tests/test_actions.py -q`

Before first test in session:
- `devenv shell -- uv sync --extra dev`

## 8. Rollout Plan

1. Branch from current mainline.
2. Implement Priority 1 first with granular commits:
   - Commit A: transport framing + diagnostics + tests.
   - Commit B: event stream terminal hardening + tests.
   - Commit C: coverage expansion for bundle/client failure paths.
   - Commit D: tuple/schema fidelity refactor + regenerated artifacts + tests.
3. Implement Priority 2/3 as separate follow-up commits (including iterator architecture normalization and timeout poisoning).
4. Keep generated code commits isolated and labeled clearly.
5. Run full quality gate before opening PR.

## 9. Acceptance Criteria

Functional:
- No regression in request/reply/event behavior.
- Framing invariant centralized in transport.
- Event stream terminal/error paths deterministic under backpressure.

Type/Schema:
- Fixed-length arrays represented or validated with fixed-length guarantees.
- Generated model API remains stable unless explicitly versioned/documented.

Quality:
- Ruff + format check clean.
- Ty check clean for interface-affecting changes.
- Targeted and full tests passing.

Docs:
- API naming behavior and deprecation path documented.
- `spawn_sh` safety caveat documented.
- Integration prerequisites documented.

## 10. Risk Register and Mitigations

Risk: Framing refactor causes double-newline or missing newline edge cases.
- Mitigation: explicit transport tests for both with/without trailing newline inputs.

Risk: Event-stream terminal signaling change introduces duplicate terminal surfacing.
- Mitigation: tests covering queue item + terminal-event interplay; ensure idempotent close semantics.

Risk: Tuple fidelity refactor breaks downstream code expecting list values.
- Mitigation: evaluate wire decode shape and document compatibility impact; consider transitional compatibility constructors if needed.

Risk: Rename of `connect()` breaks users.
- Mitigation: keep alias + deprecation window and release notes.

## 11. Execution Checklist

1. Confirm baseline test/lint/typecheck status on current branch.
2. Implement TR-2 + TR-1 (+ TR-3 if chosen) and add tests.
3. Implement API-1 hardening and race cleanup tests.
4. Add missing event-stream/bundle/client failure-path tests.
5. Implement T-4 chosen strategy and regenerate models.
6. Address ACT-1 lint conflict and action docs updates (ACT-5/S-1).
7. Implement A-2 rename with compatibility alias.
8. Apply optional cleanups (T-6, T-3, T-1, API-2 docs, TEST-6 docs).
9. Run full quality gate and full test suite.
10. Prepare PR with commit-by-commit rationale mapped to review IDs.
