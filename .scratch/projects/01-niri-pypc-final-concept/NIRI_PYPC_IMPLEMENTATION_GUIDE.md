# NIRI_PYPC_IMPLEMENTATION_GUIDE

Step-by-step implementation guide for an intern to build `niri-pypc` end-to-end from the concept and spec documents.

## Table of Contents

1. How to Use This Guide
   Execution rules, sequencing model, and quality gates that apply to every step.
2. Definition of Done
   What must be true before the implementation is considered complete.
3. Step 0: Bootstrap and Repository Orientation
   Confirm environment, repo structure, and working constraints.
4. Step 1: Package Skeleton and Tooling Baseline
   Create canonical project layout and base package files.
5. Step 2: Upstream Pin Manifest and Schema Directories
   Define pinned protocol authority and schema artifact locations.
6. Step 3: Rust Schema Exporter
   Implement and run the `niri-ipc` JSON Schema export tool.
7. Step 4: IR Normalization Tool
   Transform exported schema into deterministic generator IR.
8. Step 5: Type Generator
   Generate deterministic Pydantic protocol models from IR.
9. Step 6: Generated Verification Tool
   Add a regeneration diff-checker for CI enforcement.
10. Step 7: Type Codec Layer
   Implement externally-tagged enum encode/decode helpers.
11. Step 8: Error Taxonomy
   Implement complete `niri-pypc` exception hierarchy.
12. Step 9: Configuration Layer
   Implement config model, socket resolution, and defaults.
13. Step 10: Framing Module
   Implement newline-delimited JSON frame encode/decode.
14. Step 11: Unix Connection Transport
   Implement async Unix socket transport with limits/timeouts.
15. Step 12: Lifecycle Runtime State Machine
   Implement lifecycle transition guardrails.
16. Step 13: Command Client API (`NiriClient`)
   Implement request flow using one-connection-per-request.
17. Step 14: Event Stream API (`NiriEventStream`)
   Implement streaming reader, queueing, and backpressure modes.
18. Step 15: Bundle API (`NiriConnectionBundle`)
   Implement dual-connection convenience wrapper with isolation semantics.
19. Step 16: Public API Exports and Package Surface
   Finalize top-level re-exports and type module exports.
20. Step 17: Test Fixtures and Mock Server Infrastructure
   Build reusable testing harness for API/integration tests.
21. Step 18: Type Tests
   Add roundtrip, golden, unknown sentinel, and metadata tests.
22. Step 19: Transport and Runtime Tests
   Validate framing, connection error handling, and lifecycle invariants.
23. Step 20: API and Integration Tests
   Validate client/event/bundle behavior and socket independence.
24. Step 21: Live Tests (Optional/Gated)
   Add real compositor smoke tests gated by `NIRI_SOCKET`.
25. Step 22: Devenv Scripts and CI Gates
   Wire export/normalize/generate/verify/test/lint/typecheck workflows.
26. Step 23: Documentation and Release Readiness
   Align README/changelog/contributor docs with the pin and boundaries.
27. Step 24: Final End-to-End Verification Checklist
   Single ordered verification pass before merge.
28. Common Failure Modes and Recovery
   Practical triage notes for likely implementation issues.

## 1. How to Use This Guide

- Execute steps in order; do not skip ahead.
- Each step has:
  - `Implementation`: concrete work to perform.
  - `Verification`: tests/checks that must pass before proceeding.
- If verification fails, fix immediately and rerun that step’s checks.
- Keep generated/manual boundaries strict:
  - Generated: `src/niri_pypc/types/generated/`
  - Manual: all other package/runtime/tool modules.
- Follow repository command policy:
  - Use `devenv shell -- ...` for environment/tooling/test commands.

## 2. Definition of Done

Implementation is done only when all are true:

- Full schema -> IR -> generated type pipeline is deterministic.
- Runtime/API behavior matches spec contracts.
- Error taxonomy and lifecycle semantics are enforced.
- All required tests pass (types, transport, API, integration).
- Linting and formatting checks pass.
- Type checks pass.
- `verify-generated` passes with no diffs.
- Docs clearly communicate pin/version/boundaries.

## 3. Step 0: Bootstrap and Repository Orientation

### Implementation

1. Read and understand:
   - `NIRI_PYPC_CONCEPT_FINAL.md`
   - `NIRI_PYPC_SPEC.md`
2. Confirm package identity and constraints:
   - package name `niri-pypc`
   - import root `niri_pypc`
   - Python `3.13+`
   - asyncio-only, Unix sockets only
3. Run dependency sync (first environment-dependent command in session):
   - `devenv shell -- uv sync --extra dev`

### Verification

Run:

```bash
devenv shell -- uv sync --extra dev
```

Pass criteria:
- Sync completes successfully with no unresolved dependency errors.

---

## 4. Step 1: Package Skeleton and Tooling Baseline

### Implementation

1. Create canonical directories/files per spec:
   - `src/niri_pypc/` (with `__init__.py`, `_version.py`)
   - `src/niri_pypc/types/`, `transport/`, `runtime/`, `api/`
   - `schema/exported/`, `schema/ir/`, `schema/manifests/`
   - `tools/` with placeholders
   - `tests/` subtree by category
2. Ensure `pyproject.toml` includes package config and `tool.uv.package = true`.
3. Ensure `devenv.nix` enables Python 3.13 and Rust toolchain.

### Verification

Run:

```bash
devenv shell -- python -c "import niri_pypc; print('ok')"
devenv shell -- pytest -q
```

Pass criteria:
- Package imports.
- Empty/initial test suite runs without fatal config errors.

---

## 5. Step 2: Upstream Pin Manifest and Schema Directories

### Implementation

1. Create `schema/upstream-pin.toml`:
   - crate: `niri-ipc`
   - version: `25.11`
   - features: `json-schema`
2. Create/confirm schema artifact directories.
3. Document pin provenance in comments/docs where appropriate.

### Verification

Run:

```bash
devenv shell -- python -c "import tomllib, pathlib; p=pathlib.Path('schema/upstream-pin.toml'); d=tomllib.loads(p.read_text()); assert d['upstream']['crate']=='niri-ipc'; assert d['upstream']['version']=='25.11'; print('pin-ok')"
```

Pass criteria:
- Manifest parses.
- Pin values match concept/spec exactly.

---

## 6. Step 3: Rust Schema Exporter

### Implementation

1. Implement `tools/schema_exporter/Cargo.toml` with pinned `niri-ipc` dependency.
2. Implement `tools/schema_exporter/src/main.rs` to emit schema for:
   - `Request`, `Reply`, `Event`, `Action`
3. Support optional `--output-dir` and default to `schema/exported/`.
4. Add devenv script: `export-schema`.

### Verification

Run:

```bash
devenv shell -- export-schema
```

Then validate files:

```bash
devenv shell -- python -c "from pathlib import Path as P; req=['request.schema.json','reply.schema.json','event.schema.json','action.schema.json']; missing=[x for x in req if not (P('schema/exported')/x).exists()]; assert not missing, missing; print('schemas-ok')"
```

Pass criteria:
- All four schema files exist and are valid JSON.
- Export command exits 0.

---

## 7. Step 4: IR Normalization Tool

### Implementation

1. Implement `tools/normalize_ir.py` CLI.
2. Read upstream pin + exported schemas.
3. Resolve refs, classify types/variants, canonicalize field types.
4. Sort deterministically (types/variants/fields).
5. Write `schema/ir/niri-ipc-ir.json` with required metadata.

### Verification

Run twice and compare:

```bash
devenv shell -- normalize-ir
cp schema/ir/niri-ipc-ir.json /tmp/niri-ipc-ir.first.json
devenv shell -- normalize-ir
diff -u /tmp/niri-ipc-ir.first.json schema/ir/niri-ipc-ir.json
```

Pass criteria:
- No diff between runs.
- IR contains `ir_version`, upstream metadata, schema hashes, normalized type graph.

---

## 8. Step 5: Type Generator

### Implementation

1. Implement `tools/generate_types.py`:
   - read IR
   - emit deterministic generated files
   - include required auto-generated header metadata
2. Generate:
   - `_metadata.py`, `models.py`, `request.py`, `reply.py`, `event.py`, `action.py`, `__init__.py`
3. Implement enum model rules:
   - externally-tagged decode/encode hooks
   - inbound unknown sentinel for `Reply`/`Event`
   - strict outbound known variants
4. Add devenv script: `generate-types`.

### Verification

Run twice and compare tree hashes:

```bash
devenv shell -- generate-types
find src/niri_pypc/types/generated -type f -print0 | sort -z | xargs -0 sha256sum > /tmp/generated.first.sha
devenv shell -- generate-types
find src/niri_pypc/types/generated -type f -print0 | sort -z | xargs -0 sha256sum > /tmp/generated.second.sha
diff -u /tmp/generated.first.sha /tmp/generated.second.sha
```

Pass criteria:
- No diff in generated file checksums.
- Headers include upstream/IR/hash metadata.

---

## 9. Step 6: Generated Verification Tool

### Implementation

1. Implement `tools/verify_generated.py`:
   - generate to temp directory
   - compare file set + contents with committed generated dir
   - exit 1 with useful diff if mismatched
2. Add devenv script: `verify-generated`.

### Verification

Run:

```bash
devenv shell -- verify-generated
```

Pass criteria:
- Reports generated code is up to date and exits 0.

---

## 10. Step 7: Type Codec Layer

### Implementation

1. Implement `src/niri_pypc/types/codec.py`:
   - `decode_externally_tagged`
   - `encode_externally_tagged`
   - `unwrap_reply`
2. Ensure behavior matches spec for unit/newtype/struct variants.
3. Unknown variant fallback only when sentinel is configured.
4. Map failures to `DecodeError`/`ProtocolError`/encoding errors as defined.

### Verification

Run focused tests (create them if missing):

```bash
devenv shell -- pytest tests/types/test_roundtrip.py -q
devenv shell -- pytest tests/types/test_unknown_variants.py -q
```

Pass criteria:
- Roundtrip works for representative request/reply/event/action variants.
- Unknown inbound variants produce sentinel models (reply/event only).

---

## 11. Step 8: Error Taxonomy

### Implementation

1. Implement `src/niri_pypc/errors.py` with hierarchy:
   - `NiriError`
   - `TransportError`
   - `NiriTimeoutError` (`NiriError` + `TimeoutError`)
   - `DecodeError`
   - `ProtocolError`
   - `RemoteError`
   - `LifecycleError`
   - `ConfigError`
   - `InternalError`
2. Add optional context fields (operation, path, state, retryable, cause, payload excerpt).

### Verification

Run or add tests:

```bash
devenv shell -- pytest tests/api/test_errors.py -q
```

Pass criteria:
- Class inheritance and context behavior match spec.
- `NiriTimeoutError` is catchable as `TimeoutError`.

---

## 12. Step 9: Configuration Layer

### Implementation

1. Implement `src/niri_pypc/config.py`:
   - `NiriConfig`
   - `BackpressureMode`
2. Defaults:
   - connect timeout 5.0
   - request timeout 10.0
   - event read timeout `None`
   - max frame size 4 MiB
   - queue capacity 256
3. Implement socket path resolution precedence:
   - explicit config path
   - `NIRI_SOCKET`
   - else `ConfigError`

### Verification

Run:

```bash
devenv shell -- pytest tests/api/test_config.py -q
```

Pass criteria:
- Defaults, env fallback, and error path all verified.

---

## 13. Step 10: Framing Module

### Implementation

1. Implement `src/niri_pypc/transport/framing.py`:
   - `encode_frame(data) -> bytes` newline-terminated JSON
   - `decode_frame(raw) -> Any`
2. Use compact JSON separators for deterministic wire formatting.
3. Raise `DecodeError` on malformed JSON.

### Verification

Run:

```bash
devenv shell -- pytest tests/transport/test_framing.py -q
```

Pass criteria:
- Encode/decode correctness.
- Invalid JSON path raises expected error type.

---

## 14. Step 11: Unix Connection Transport

### Implementation

1. Implement `src/niri_pypc/transport/connection.py` `UnixConnection`.
2. Required methods:
   - `connect(...)`
   - `write_frame(...)`
   - `read_frame(...)` with max-size and timeout handling
   - `close()` idempotent
3. Map connection/read/write failures into taxonomy.

### Verification

Run:

```bash
devenv shell -- pytest tests/transport/test_connection.py -q
```

Pass criteria:
- Connect timeout/error paths validated.
- Oversize frame and EOF behaviors validated.
- Close is idempotent.

---

## 15. Step 12: Lifecycle Runtime State Machine

### Implementation

1. Implement `src/niri_pypc/runtime/lifecycle.py`:
   - `LifecycleState` enum
   - `LifecycleManager`
2. Enforce valid transition graph from spec.
3. Guard with lock for task safety.
4. Provide convenience checks (`is_usable`, `is_terminal`, `require_state`).

### Verification

Run:

```bash
devenv shell -- pytest tests/api/test_lifecycle.py -q
```

Pass criteria:
- Valid transitions pass.
- Invalid transitions raise `LifecycleError`.

---

## 16. Step 13: Command Client API (`NiriClient`)

### Implementation

1. Implement `src/niri_pypc/api/client.py`.
2. Use one-connection-per-request model:
   - open socket
   - encode request
   - write frame
   - read reply
   - decode + unwrap `Ok/Err`
   - close socket
3. Enforce close semantics:
   - closed client rejects further requests with `LifecycleError`.
4. Add async context manager support.

### Verification

Run:

```bash
devenv shell -- pytest tests/api/test_client.py -q
```

Pass criteria:
- Happy path returns decoded `Ok` payload.
- `Err` maps to `RemoteError`.
- Timeout/cancellation/closed-state behavior correct.

---

## 17. Step 14: Event Stream API (`NiriEventStream`)

### Implementation

1. Implement `src/niri_pypc/api/event_stream.py`.
2. On connect:
   - open connection
   - send EventStream request
   - start background reader task
3. Reader task behavior:
   - decode each inbound event
   - push into bounded queue
   - enforce backpressure mode
4. API methods:
   - `next(timeout=...)`
   - async iterator (`__aiter__`, `__anext__`)
   - `close()` idempotent, cancellation-safe
5. Ensure no post-close event emission.

### Verification

Run:

```bash
devenv shell -- pytest tests/api/test_event_stream.py -q
```

Pass criteria:
- Ordered event delivery.
- Backpressure behavior matches mode.
- Stream closes predictably on EOF/errors/cancellation.

---

## 18. Step 15: Bundle API (`NiriConnectionBundle`)

### Implementation

1. Implement `src/niri_pypc/api/bundle.py` with:
   - `open(config)`
   - `.client` and `.events` properties
   - idempotent `close()`
2. Enforce bundle semantics:
   - convenience wrapper only
   - command and event channels remain independent
   - one side failing does not auto-close the other
3. Add async context manager support.

### Verification

Run:

```bash
devenv shell -- pytest tests/api/test_bundle.py -q
```

Pass criteria:
- Open/close behavior is correct.
- Error isolation between client and stream is validated.

---

## 19. Step 16: Public API Exports and Package Surface

### Implementation

1. Finalize `src/niri_pypc/__init__.py` exports:
   - config, errors, client/event/bundle classes
2. Finalize `src/niri_pypc/types/__init__.py` exports:
   - generated models
   - codec helpers
3. Ensure import conventions from spec examples work.

### Verification

Run:

```bash
devenv shell -- python - <<'PY'
from niri_pypc import NiriClient, NiriConfig, NiriError
from niri_pypc.types import Request, Event, Action
print('imports-ok')
PY
```

Pass criteria:
- Public imports resolve without private-path access.

---

## 20. Step 17: Test Fixtures and Mock Server Infrastructure

### Implementation

1. Implement shared fixtures (`tests/conftest.py`) and per-suite fixtures.
2. Build integration mock Unix socket server fixture:
   - handles command mode and event-stream mode
   - records requests
   - supports canned responses/events
3. Add helper utilities for frame send/receive in tests.

### Verification

Run:

```bash
devenv shell -- pytest tests/integration -q -k conftest
```

Pass criteria:
- Fixtures initialize and teardown cleanly.
- Mock server reliably handles both command and event flows.

---

## 21. Step 18: Type Tests

### Implementation

1. Add/complete:
   - `tests/types/test_roundtrip.py`
   - `tests/types/test_golden.py`
   - `tests/types/test_unknown_variants.py`
   - `tests/types/test_edge_cases.py`
   - `tests/types/test_metadata.py`
2. Validate serializer and validator behavior for generated enums.

### Verification

Run:

```bash
devenv shell -- pytest tests/types -q
```

Pass criteria:
- All type-level encode/decode invariants hold.
- Metadata/provenance values are present and coherent.

---

## 22. Step 19: Transport and Runtime Tests

### Implementation

1. Add/complete transport tests:
   - framing parse failures
   - oversize frame rejection
   - timeout and EOF paths
2. Add/complete runtime lifecycle tests for allowed/blocked transitions.

### Verification

Run:

```bash
devenv shell -- pytest tests/transport tests/api/test_lifecycle.py -q
```

Pass criteria:
- Transport and lifecycle invariants are covered and passing.

---

## 23. Step 20: API and Integration Tests

### Implementation

1. Add/complete:
   - `tests/api/test_client.py`
   - `tests/api/test_event_stream.py`
   - `tests/api/test_bundle.py`
2. Add/complete integration tests:
   - command flow
   - event flow
   - command/event independence

### Verification

Run:

```bash
devenv shell -- pytest tests/api tests/integration -q
```

Pass criteria:
- API contracts match spec behavior.
- Integration tests validate end-to-end request/event handling over Unix socket mock.

---

## 24. Step 21: Live Tests (Optional/Gated)

### Implementation

1. Add `tests/live/` with skip-if-`NIRI_SOCKET` gate.
2. Implement minimal real compositor checks (e.g., version request).
3. Ensure CI default excludes live tests unless explicitly enabled.

### Verification

Run (in live niri session only):

```bash
devenv shell -- pytest tests/live -q
```

Pass criteria:
- Tests skip cleanly when socket missing.
- Smoke tests pass when real socket is present.

---

## 25. Step 22: Devenv Scripts and CI Gates

### Implementation

1. Ensure devenv scripts exist and work:
   - `export-schema`, `normalize-ir`, `generate-types`, `verify-generated`, `regen-all`
2. Configure CI to run required gates in order:
   - export schema
   - normalize IR
   - generate types
   - verify generated
   - tests
   - lint
   - format check
   - type check
3. Add guardrails against manual edits in generated subtree.

### Verification

Run:

```bash
devenv shell -- export-schema
devenv shell -- normalize-ir
devenv shell -- generate-types
devenv shell -- verify-generated
devenv shell -- pytest -q
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- ty check .
```

Pass criteria:
- All commands pass without errors.

---

## 26. Step 23: Documentation and Release Readiness

### Implementation

1. Update README with:
   - pinned `niri-ipc 25.11`
   - typed raw event delivery scope
   - non-goals (no state engine, no auto-reconnect)
2. Add contributor instructions for pin bump and regeneration flow.
3. Update changelog/release notes template to include:
   - upstream pin
   - schema/IR/generator changes
   - API/runtime compatibility notes

### Verification

Manual checklist:

- README examples compile conceptually against actual API names.
- Regeneration instructions are executable as written.
- Release notes include all required compatibility metadata.

---

## 27. Step 24: Final End-to-End Verification Checklist

Run this exact sequence before declaring complete:

```bash
devenv shell -- uv sync --extra dev
devenv shell -- export-schema
devenv shell -- normalize-ir
devenv shell -- generate-types
devenv shell -- verify-generated
devenv shell -- pytest -q
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- ty check .
```

Completion criteria:
- Entire pipeline green.
- No generated diffs.
- No failing tests/checks.

## 28. Common Failure Modes and Recovery

1. `verify-generated` fails unexpectedly
- Cause: nondeterministic generator output, stale IR, or manual edit in generated files.
- Recovery:
  - rerun `normalize-ir` and `generate-types`
  - inspect stable ordering and hash header generation
  - remove nondeterministic values (timestamps, unordered dict writes)

2. Unknown event/reply breaks decode
- Cause: inbound variant not recognized and sentinel fallback missing.
- Recovery:
  - ensure fallback path is enabled for inbound `Reply` and `Event`
  - keep outbound strict

3. Intermittent event test failures
- Cause: race conditions in background reader or close/cancel sequencing.
- Recovery:
  - enforce lifecycle transition order
  - add deterministic teardown/drain behavior
  - avoid un-awaited background tasks in tests

4. Socket resolution failures in tests
- Cause: `NIRI_SOCKET` not set and config not passed explicitly.
- Recovery:
  - in unit/integration tests, always provide explicit temporary socket path via `NiriConfig`

5. Backpressure behavior mismatch
- Cause: queue-full handling not matching selected mode.
- Recovery:
  - assert explicit branch behavior in tests for both `DROP_OLDEST` and `FAIL_FAST`

6. Type-check/lint drift after generation updates
- Cause: generator emits code not aligned with current style/type constraints.
- Recovery:
  - update generator templates, regenerate, and re-run all quality gates

This guide is authoritative for intern execution order. If concept/spec conflicts appear during implementation, follow `NIRI_PYPC_SPEC.md` for concrete behavior and update docs immediately to remove ambiguity.
