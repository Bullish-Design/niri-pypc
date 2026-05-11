# NIRI_PYPC_CONCEPT_FINAL

## Table of Contents

1. Authority and Purpose
   Final scope and normative status of this document.
2. Ecosystem Role and Library Boundary
   Explicit responsibility split between `niri-pypc` and downstream libraries including `niri-state`.
3. Project Identity
   Naming and import-root conventions.
4. Core Goals
   Required outcomes for correctness, reproducibility, and runtime behavior.
5. Non-Goals
   Out-of-scope functionality, including state ownership and policy layers.
6. Upstream Authority and Pinning
   Protocol source-of-truth and pin management rules.
7. Supported Platforms and Runtime Assumptions
   Python version, async model, and OS/socket support contract.
8. High-Level Architecture
   Generated protocol layer vs hand-written runtime/client layers.
9. Repository Layout
   Canonical repository structure.
10. External and Internal Dependency Rules
   Layering constraints inside `niri-pypc` and across `niri-state`.
11. Schema Export and IR Workflow
   Export pipeline, normalization, and committed artifacts.
12. Generation Contract
   Determinism, failure behavior, metadata, and manual-edit boundaries.
13. Type System and Unknown Variant Policy
   Pydantic model strategy and strict/unknown handling.
14. Encoding and Decoding Ownership
   Responsibilities of `types/codec.py`, generated modules, and runtime.
15. Configuration and Socket Discovery Policy
   Config ownership, precedence order, and runtime defaults.
16. Runtime and Transport Design
   Lifecycle states, framing, in-flight settlement, and close semantics.
17. Concurrency and Task-Safety Contract
   Explicit rules for concurrent requests, stream consumers, and cross-task close.
18. Event Stream Delivery and Backpressure Policy
   Buffering, ordering, overflow behavior, and cancellation semantics.
19. Version-Mismatch Compatibility Policy
   Behavior when runtime compositor protocol and pinned protocol differ.
20. Public API Concept
   Client, event stream, and dual-connection bundle abstractions.
21. Error Taxonomy
   Distinction between transport/decode/lifecycle and remote semantic failures.
22. Testing Strategy
   Type, transport, API, integration, live, and explicit state-test exclusions.
23. CI Quality Gates
   Required checks for reproducibility and correctness.
24. Release and Versioning Policy
   Release note requirements and compatibility declarations.
25. Documentation Plan
   Required docs and user-facing expectation setting.
26. Implementation Phases
   Ordered plan for building the project from skeleton to full runtime.
27. Design Principles to Preserve
   Guardrails for future changes.
28. Final Recommendation
   Concise statement of the intended long-term shape.

## 1. Authority and Purpose

This document is the normative guiding concept for `niri-pypc`.

It defines the final architectural, protocol, runtime, testing, and release decisions for the project, superseding ambiguous or conflicting language from earlier drafts.

## 2. Ecosystem Role and Library Boundary

`niri-pypc` is the pinned protocol and runtime substrate for Niri IPC in Python.

It owns:
- protocol model generation from pinned upstream schema
- protocol encode/decode correctness
- command/event socket runtime behavior
- typed event delivery contract

It does not own:
- persistent or canonical compositor state stores
- event reducers/selectors/snapshots
- replay/convergence/wait-until state engines
- higher-level reconciliation policy

Those concerns belong to downstream libraries, including `niri-state`.

Boundary contract:
- `niri-pypc` delivers typed protocol events and request/response primitives.
- `niri-state` consumes those typed events and derives state.

## 3. Project Identity

- Project name: `niri-pypc`
- Import root: `niri_pypc`

## 4. Core Goals

1. Pinned upstream correctness against one exact `niri-ipc` crate version.
2. Strict separation of generated protocol types and hand-written runtime behavior.
3. Deterministic, reproducible generation and verification workflows.
4. High-confidence typing for requests, responses, events, and domain models.
5. Runtime correctness for sockets, framing, cancellation, timeouts, and lifecycle.
6. Pythonic API ergonomics without hiding protocol realities.

## 5. Non-Goals

1. Backward compatibility with prior Nim/Python libraries.
2. Runtime abstraction across multiple async backends.
3. Automatic support for unpinned upstream protocol changes.
4. Code generation of transport/runtime lifecycle logic.
5. UI/business-policy helpers unrelated to raw IPC.
6. Owning a compositor state-reduction engine.
7. Reducer/selector/snapshot/replay/convergence logic.
8. Sync API support (asyncio-only scope).

## 6. Upstream Authority and Pinning

Authoritative source:
- Rust crate: `niri-ipc = <PINNED_VERSION>`

Rules:
1. Upstream crate semantics are canonical for protocol structure.
2. The pinned version is explicit in-repo.
3. Generated protocol artifacts derive only from that pin.
4. Pin bumps are deliberate changes with regeneration and test updates.
5. Releases state the exact upstream pin.

## 7. Supported Platforms and Runtime Assumptions

1. Python: 3.13+.
2. Validation models: Pydantic v2.
3. Async runtime: `asyncio` only.
4. OS support: Linux/Unix environments where Unix domain sockets are available.
5. No windows support, no specific MacOS support. 

## 8. High-Level Architecture

Two major concerns in one repository:

1. Generated protocol types (`src/niri_pypc/types/generated/`):
- protocol models
- request/action/response/event definitions
- generated wire-name maps and tagged-union adapters
- generated metadata

2. Hand-written runtime/client code:
- socket management
- framing/buffering
- timeout/cancellation/lifecycle
- command and event APIs
- optional dual-connection convenience wrapper

Hard rule:
- generated code defines wire contract
- manual code defines runtime behavior

## 9. Repository Layout

```text
niri-pypc/
├─ devenv.nix
├─ devenv.yaml
├─ pyproject.toml
├─ README.md
├─ CHANGELOG.md
├─ tools/
│  ├─ schema_exporter/
│  ├─ generate_types.py
│  ├─ verify_generated.py
│  └─ fixtures/
├─ schema/
│  ├─ upstream-pin.toml
│  ├─ exported/
│  │  ├─ niri-ipc-schema.json
│  │  └─ niri-ipc-ir.json
│  └─ manifests/
├─ src/
│  └─ niri_pypc/
│     ├─ __init__.py
│     ├─ errors.py
│     ├─ config.py
│     ├─ types/
│     │  ├─ __init__.py
│     │  ├─ codec.py
│     │  ├─ helpers.py
│     │  └─ generated/
│     ├─ transport/
│     ├─ runtime/
│     └─ api/
└─ tests/
   ├─ types/
   ├─ transport/
   ├─ api/
   ├─ integration/
   ├─ live/
   └─ fixtures/
```

## 10. External and Internal Dependency Rules

Internal:
- `api -> transport, runtime, types, errors`
- `transport -> runtime, errors`
- `runtime -> errors`
- `types -> (internal type helpers only)`
- `errors -> no internal deps`

Cross-library:
- `niri-state -> niri-pypc`
- Applications may depend on both.
- `niri-pypc` must not depend on `niri-state`.

## 11. Schema Export and IR Workflow

Pinned manifest:
- `schema/upstream-pin.toml`

Rust exporter responsibilities:
1. Depend on exact pinned `niri-ipc`.
2. Enable required upstream schema feature(s).
3. Emit stable machine-readable schema artifacts.
4. Normalize output into IR for deterministic Python generation.

Committed artifacts:
- exporter source
- pinned manifest
- exported schema JSON
- normalized IR JSON
- generated Python code
- deterministic fixtures/manifests used by tests

## 12. Generation Contract

Inputs:
- pinned manifest
- exported schema
- normalized IR
- generator logic/templates

Outputs:
- generated protocol modules
- generated metadata
- optional deterministic fixture manifests

Invariants:
1. Same input produces byte-for-byte identical output.
2. Generated files carry explicit generated headers.
3. Manual edits inside generated files are forbidden.
4. Unsupported schema shapes hard-fail generation.
5. IR has explicit schema versioning.
6. Name normalization, reserved-word handling, and ordering are deterministic.

Determinism decision:
- No wall-clock timestamps in committed generated artifacts.
- Metadata may include stable provenance only: upstream crate/version, generator version, schema hash, IR hash, and optional source commit if part of actual input.

## 13. Type System and Unknown Variant Policy

Type layer uses Pydantic models consistently.

Priorities:
1. Strong typing over ad-hoc dicts.
2. Explicit optionality and nullability semantics.
3. Stable tagged-union decoding.
4. Deterministic encode/decode behavior.

Unknown variant policy (final):
- Outbound requests/actions: strict, no unknown outbound variants.
- Inbound responses/events: decode into explicit typed `Unknown*` sentinels carrying raw payload.

Rationale:
- outbound must always match pinned contract
- inbound unknowns are valuable diagnostics for mismatch/additive evolution

## 14. Encoding and Decoding Ownership

`types/codec.py` owns:
- shared encode/decode helpers
- tagged-variant dispatch primitives
- common adapter behavior
- raw payload fallback helpers for unknown sentinels

Generated modules own:
- model declarations
- per-surface typed parse/serialize entrypoints
- wire-name mappings

Runtime owns:
- frame I/O and buffering
- invoking type decode/encode
- mapping validation failures into runtime error taxonomy

## 15. Configuration and Socket Discovery Policy

`config.py` owns:
- socket path resolution
- timeout defaults and overrides
- framing limits
- event buffering limits

Socket path discovery precedence:
1. Explicit constructor/config argument.
2. Explicit environment variable override (documented canonical env var).
3. Library default discovery mechanism.

Timeout config:
- connect timeout
- request timeout
- event read timeout (or per-read override)

Framing/backpressure config:
- max frame size
- event queue capacity

## 16. Runtime and Transport Design

Core concerns:
1. Unix socket connection establishment
2. newline-delimited frame parsing
3. bounded buffering and max-frame enforcement
4. timeout and cancellation
5. idempotent close
6. deterministic settlement of in-flight operations
7. command and event connection independence

Lifecycle states:
- `init`
- `connecting`
- `ready`
- `closing`
- `closed`

Invariants:
1. `close()` is idempotent.
2. New operations rejected once closing starts.
3. In-flight operations settle deterministically.
4. No post-closed response/event emission.

## 17. Concurrency and Task-Safety Contract

1. Multiple concurrent `request()` calls are supported on one client if connection is `ready`.
2. `close()` may be called from a different task; it transitions to `closing` and settles in-flight work deterministically.
3. Event stream consumer model is single-consumer per stream instance.
4. Multiple consumers require explicit fan-out implemented by caller or separate stream instances.
5. Shared client objects across tasks are supported only within defined request/close semantics; undefined concurrent mutation is forbidden.

## 18. Event Stream Delivery and Backpressure Policy

1. Event ordering is preserved as received from wire.
2. Buffering is bounded by configured queue capacity.
3. Overflow behavior default: fail-fast by closing stream with explicit backpressure error.
4. No silent event drop in default mode.
5. API supports async iterator and explicit `next()` forms.
6. Cancellation during await read exits predictably and preserves lifecycle invariants.

## 19. Version-Mismatch Compatibility Policy

Because `niri-pypc` is pinned, mismatch behavior is explicit:

1. On connect/handshake, library performs best available version capability check.
2. If hard mismatch is detected and policy is strict mode (default), fail fast with compatibility error.
3. Optional relaxed mode may continue, but only with clear warning surface and unknown inbound sentinel handling.
4. Outbound requests/actions always remain strict to pinned contract.

## 20. Public API Concept

Client:

```python
async with NiriClient.connect(config) as client:
    version = await client.request(VersionRequest())
    outputs = await client.request(OutputsRequest())
```

Event stream:

```python
async with NiriEventStream.subscribe(config) as stream:
    event = await stream.next(timeout=5.0)
```

Dual-channel convenience wrapper:

```python
async with NiriConnectionBundle.open(config) as bundle:
    version = await bundle.client.request(VersionRequest())
    event = await bundle.events.next(timeout=5.0)
```

Naming decision:
- Prefer `NiriConnectionBundle` over `NiriSession` to avoid state-store implications.
- This object coordinates sockets only; it does not maintain derived compositor state.

## 21. Error Taxonomy

Required categories:
1. `TransportError` for socket/framing I/O failures.
2. `TimeoutError` for connect/request/event timeouts.
3. `DecodeError` for shape/validation failures during decode.
4. `ProtocolError` for wire-level contract violations.
5. `RemoteSemanticError` for handled semantic errors returned by compositor.
6. `LifecycleError` for invalid state transitions/usage.
7. `ConfigError` for invalid or unresolved configuration.
8. `InternalInvariantError` for impossible internal states.

Context fields should include:
- operation name
- socket path
- lifecycle state
- retryability hint
- wrapped cause
- bounded raw payload excerpt when relevant

## 22. Testing Strategy

`tests/types/`:
- roundtrip encode/decode tests
- golden fixtures
- unknown variant behavior tests
- null/missing/empty semantics
- metadata/provenance checks
- drift detection

`tests/transport/`:
- partial/multi-frame reads
- oversize frame rejection
- malformed framing
- disconnect mid-frame

`tests/api/`:
- request/response happy path
- timeout/cancellation/close behavior
- open/close repetition

`tests/integration/`:
- mock socket server behavior
- event sequencing
- decode failure paths
- command/event socket independence

`tests/live/`:
- gated by environment (`NIRI_SOCKET`)
- version query and basic behavior checks

Explicit exclusion:
- reducer/selector/replay/convergence/state-store tests belong in `niri-state`, not `niri-pypc`.

## 23. CI Quality Gates

Required:
1. Schema export succeeds.
2. Type generation succeeds.
3. `verify-generated` passes with no diff.
4. Type test suite passes.
5. Transport/API/integration suites pass.
6. Lint/type checks pass.
7. Guardrails prevent manual edits in generated subtree and forbidden dependency directions.

Optional:
- live smoke tests where environment permits
- fixture hash verification
- decode-path benchmarks

## 24. Release and Versioning Policy

Release notes must include:
- `niri-pypc` version
- pinned `niri-ipc` version
- schema/IR format changes
- generated artifact changes
- runtime API changes
- compatibility policy notes

Versioning can follow normal Python package semantics, but upstream pin compatibility must always be explicit.

## 25. Documentation Plan

Required docs:
1. High-level README
2. Generation workflow guide
3. Contributor guide for pin updates
4. API examples for client and event stream usage
5. Generated vs hand-written boundary guide

README must explicitly state:
- pinned protocol alignment
- raw typed event delivery (not reduced state)
- dual-channel connection model
- recommendation to use `niri-state` for derived live compositor state

## 26. Implementation Phases

Phase A: repository skeleton and pinned manifest.

Phase B: Rust schema exporter and stable schema/IR artifacts.

Phase C: deterministic Python type generation and metadata.

Phase D: exhaustive type-layer tests and drift verification.

Phase E: transport/runtime implementation and tests.

Phase F: client/event/bundle APIs and integration tests.

Exit criteria for each phase must be testable and enforced in CI.

## 27. Design Principles to Preserve

1. Protocol-first correctness over convenience.
2. Generated protocol contract, manual runtime semantics.
3. Reproducibility and deterministic generation.
4. Explicit lifecycle and error behavior.
5. No hidden magic around dual-channel semantics.
6. Clear layering: `niri-pypc` substrate, `niri-state` state engine.

## 28. Final Recommendation

Build `niri-pypc` as a narrow, strict, pinned protocol/runtime library with deterministic generated types and hand-written socket/runtime behavior.

Keep event delivery typed and raw, keep state derivation out of scope, and formalize `niri-state` as the downstream state layer.

That structure maximizes correctness, maintainability, reviewability, and long-term composability.
