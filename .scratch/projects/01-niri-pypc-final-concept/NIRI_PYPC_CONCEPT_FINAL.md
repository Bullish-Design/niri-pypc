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
   Protocol source-of-truth, pin version, and pin management rules.
7. Upstream Wire Protocol Facts
   Concrete protocol mechanics as implemented by niri.
8. Supported Platforms and Runtime Assumptions
   Python version, async model, and OS/socket support contract.
9. High-Level Architecture
   Generated protocol layer vs hand-written runtime/client layers.
10. Repository Layout
    Canonical repository structure.
11. External and Internal Dependency Rules
    Layering constraints inside `niri-pypc` and across `niri-state`.
12. Schema Export Pipeline
    Rust exporter, `schemars` integration, devenv script, and committed artifacts.
13. IR Normalization
    Transformation from JSON Schema to generator-ready IR.
14. Generation Contract
    Determinism, failure behavior, metadata, and manual-edit boundaries.
15. Type System and Pydantic Strategy
    Pydantic model conventions, discriminated unions, and unknown variant policy.
16. Encoding and Decoding Ownership
    Responsibilities of codec helpers, generated modules, and runtime.
17. Configuration and Socket Discovery Policy
    Config ownership, precedence order, and runtime defaults.
18. Runtime and Transport Design
    Lifecycle states, framing, in-flight settlement, and close semantics.
19. Concurrency and Task-Safety Contract
    Explicit rules for concurrent requests, stream consumers, and cross-task close.
20. Event Stream Delivery and Backpressure Policy
    Buffering, ordering, overflow behavior, and cancellation semantics.
21. Version-Mismatch Compatibility Policy
    Behavior when runtime compositor protocol and pinned protocol differ.
22. Reconnection Policy
    Explicit stance on automatic reconnection.
23. Public API Concept
    Client, event stream, and dual-connection bundle abstractions.
24. Error Taxonomy
    Distinction between transport/decode/lifecycle and remote semantic failures.
25. Testing Strategy
    Type, transport, API, integration, live, and explicit state-test exclusions.
26. CI Quality Gates
    Required checks for reproducibility and correctness.
27. Release and Versioning Policy
    Release note requirements and compatibility declarations.
28. Documentation Plan
    Required docs and user-facing expectation setting.
29. Implementation Phases
    Ordered plan for building the project from skeleton to full runtime.
30. Design Principles to Preserve
    Guardrails for future changes.
31. Final Recommendation
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
9. Automatic reconnection (see Section 22).

## 6. Upstream Authority and Pinning

Authoritative source:
- Rust crate: `niri-ipc = "25.11"`

Rules:
1. Upstream crate semantics are canonical for protocol structure.
2. The pinned version (`25.11`) is recorded in `schema/upstream-pin.toml` and in the exporter's `Cargo.toml`.
3. Generated protocol artifacts derive only from that pin.
4. Pin bumps are deliberate changes with regeneration and test updates.
5. Releases state the exact upstream pin.

## 7. Upstream Wire Protocol Facts

This section documents the concrete IPC protocol as implemented by the niri compositor. The transport layer depends directly on these facts.

Socket discovery:
- Niri exposes its IPC socket path via the `NIRI_SOCKET` environment variable, set automatically for processes launched within a niri session.

Connection model:
- A single Unix domain socket path serves both command and event connections.
- The client connects, sends a request, and receives a response — one request/response per connection for commands.
- For events, the client sends an `EventStream` request and then receives a continuous stream of newline-delimited JSON event objects on that same connection until the connection is closed.
- Command and event connections are independent socket connections to the same socket path.

Wire format:
- Newline-delimited JSON (`\n`-terminated).
- Requests are serialized as JSON using serde's default externally-tagged enum format (e.g., `{"Action": {"FocusWindow": {...}}}`).
- Responses are JSON objects. Successful responses contain `"Ok"` with the result payload; error responses contain `"Err"` with a string message.
- Events are serialized as externally-tagged JSON objects, one per line.

Serde tagging:
- `niri-ipc` uses serde's default externally-tagged representation for its Rust enums. A variant like `Request::Action(Action)` serializes as `{"Action": <action_payload>}`.
- Struct variants serialize with their fields as a JSON object value.
- Tuple variants with a single field serialize with that field as the value.
- Unit variants serialize as a plain JSON string (e.g., `"Version"`).

## 8. Supported Platforms and Runtime Assumptions

1. Python: 3.13+.
2. Validation models: Pydantic v2.
3. Async runtime: `asyncio` only.
4. OS support: Linux/Unix environments where Unix domain sockets are available.
5. No Windows support, no specific macOS support.

## 9. High-Level Architecture

Two major concerns in one repository:

1. Generated protocol types (`src/niri_pypc/types/generated/`):
- protocol models (Pydantic `BaseModel` subclasses)
- request/action/response/event definitions
- generated wire-name maps and Pydantic discriminated union adapters
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

## 10. Repository Layout

```text
niri-pypc/
├─ devenv.nix
├─ devenv.yaml
├─ pyproject.toml
├─ README.md
├─ CHANGELOG.md
├─ tools/
│  ├─ schema_exporter/          # Rust binary crate
│  │  ├─ Cargo.toml
│  │  └─ src/
│  │     └─ main.rs
│  ├─ generate_types.py
│  ├─ normalize_ir.py
│  ├─ verify_generated.py
│  └─ fixtures/
├─ schema/
│  ├─ upstream-pin.toml
│  ├─ exported/
│  │  ├─ request.schema.json
│  │  ├─ reply.schema.json
│  │  ├─ event.schema.json
│  │  └─ action.schema.json
│  ├─ ir/
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

## 11. External and Internal Dependency Rules

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

## 12. Schema Export Pipeline

The schema export step converts the pinned `niri-ipc` Rust crate into machine-readable JSON Schema artifacts.

Mechanism:
- `niri-ipc` supports the `json-schema` cargo feature, which enables `schemars` `JsonSchema` derives on all protocol types.
- A small Rust binary in `tools/schema_exporter/` depends on the pinned crate version and uses `schemars::schema_for!()` to emit JSON Schema for each top-level protocol type.

Exporter Rust binary (`tools/schema_exporter/src/main.rs`):
```rust
use niri_ipc::{Request, Reply, Event, Action};
use schemars::schema_for;

fn main() {
    let types: &[(&str, serde_json::Value)] = &[
        ("request", serde_json::to_value(schema_for!(Request)).unwrap()),
        ("reply", serde_json::to_value(schema_for!(Reply)).unwrap()),
        ("event", serde_json::to_value(schema_for!(Event)).unwrap()),
        ("action", serde_json::to_value(schema_for!(Action)).unwrap()),
    ];
    for (name, schema) in types {
        let path = format!("schema/exported/{name}.schema.json");
        std::fs::write(&path, serde_json::to_string_pretty(schema).unwrap()).unwrap();
    }
}
```

Exporter `Cargo.toml`:
```toml
[package]
name = "niri-ipc-schema-exporter"
version = "0.1.0"
edition = "2021"

[dependencies]
niri-ipc = { version = "=25.11", features = ["json-schema"] }
schemars = "0.8"
serde_json = "1.0"
```

Devenv integration:
- `devenv.nix` adds Rust toolchain (`rustc`, `cargo`) to the dev environment.
- A devenv script `export-schema` runs `cargo run` inside `tools/schema_exporter/` and writes output to `schema/exported/`.

Pinned manifest (`schema/upstream-pin.toml`):
```toml
[upstream]
crate = "niri-ipc"
version = "25.11"
features = ["json-schema"]
```

Committed artifacts:
- exporter source (`tools/schema_exporter/`)
- pinned manifest (`schema/upstream-pin.toml`)
- exported JSON Schema files (`schema/exported/*.schema.json`)
- normalized IR (`schema/ir/niri-ipc-ir.json`)
- generated Python code (`src/niri_pypc/types/generated/`)

## 13. IR Normalization

The raw JSON Schema output from `schemars` is rich but not directly suitable for deterministic Python code generation. A normalization step transforms it into a stable intermediate representation (IR).

Pipeline:
1. `tools/normalize_ir.py` reads all `schema/exported/*.schema.json` files.
2. It resolves `$ref` references, flattens `definitions`, and normalizes into a canonical IR shape.
3. Output is written to `schema/ir/niri-ipc-ir.json`.

IR structure (conceptual):
```json
{
  "ir_version": "1",
  "upstream_crate": "niri-ipc",
  "upstream_version": "25.11",
  "schema_hashes": { "request": "sha256:...", "reply": "sha256:...", ... },
  "enums": [
    {
      "name": "Request",
      "tag_type": "external",
      "variants": [
        { "name": "Version", "kind": "unit" },
        { "name": "Action", "kind": "newtype", "inner": "Action" },
        ...
      ]
    },
    ...
  ],
  "structs": [
    {
      "name": "Output",
      "fields": [
        { "name": "name", "type": "string", "optional": false },
        { "name": "logical", "type": "LogicalOutput", "optional": true },
        ...
      ]
    },
    ...
  ]
}
```

Invariants:
1. IR normalization is deterministic: same schema input produces identical IR output.
2. IR has explicit versioning (`ir_version`) to detect format changes.
3. Schema hashes are included for drift detection.
4. Enum variants are sorted in a stable, deterministic order.

## 14. Generation Contract

Inputs:
- pinned manifest
- normalized IR (`schema/ir/niri-ipc-ir.json`)
- generator logic (`tools/generate_types.py`)

Outputs:
- generated protocol modules (`src/niri_pypc/types/generated/`)
- generated metadata (`src/niri_pypc/types/generated/_metadata.py`)
- optional deterministic fixture manifests

Invariants:
1. Same input produces byte-for-byte identical output.
2. Generated files carry explicit generated headers (e.g., `# AUTO-GENERATED — DO NOT EDIT`).
3. Manual edits inside generated files are forbidden.
4. Unsupported schema shapes hard-fail generation.
5. IR has explicit schema versioning.
6. Name normalization (PascalCase types, snake_case fields), reserved-word handling, and ordering are deterministic.

Determinism decision:
- No wall-clock timestamps in committed generated artifacts.
- Metadata may include stable provenance only: upstream crate/version, generator version, schema hash, IR hash.

## 15. Type System and Pydantic Strategy

All protocol types are Pydantic v2 `BaseModel` subclasses. The generator and hand-written codec should maximize use of native Pydantic features.

Pydantic features to use:
1. **Discriminated unions** via `Discriminator` and `Tag` for tagged enums where Pydantic's native support fits. For externally-tagged serde enums (where the JSON key is the discriminator), use custom validators or a thin codec adapter since Pydantic's built-in discriminator expects a field value, not a key.
2. **`model_validator(mode="wrap")`** or **`model_validator(mode="before")`** for externally-tagged enum decoding — intercept raw dict, extract the single key, and dispatch to the correct variant model.
3. **`Field(alias=...)`** for wire-name to Python-name mapping where names differ.
4. **`model_config = ConfigDict(populate_by_name=True, strict=False)`** to allow both alias and Python-name access.
5. **`model_serializer`** for controlling outbound JSON shape (re-wrapping into externally-tagged form).
6. **Standard field types** (`str`, `int`, `float`, `bool`, `list[T]`, `T | None`) mapped directly from schema.
7. **Nested models** for struct types.
8. **`Annotated[...]`** with Pydantic metadata for constraints where applicable.

Unknown variant policy (final):
- Outbound requests/actions: strict, no unknown outbound variants.
- Inbound responses/events: decode into explicit typed `Unknown*` sentinel models carrying raw payload. The `model_validator` fallback path creates these when no known variant matches.

Rationale:
- Outbound must always match pinned contract.
- Inbound unknowns are valuable diagnostics for version mismatch / additive evolution.

## 16. Encoding and Decoding Ownership

`types/codec.py` owns:
- externally-tagged enum decode dispatcher (given a `dict` with one key, resolve to variant model)
- externally-tagged enum encode helper (wrap variant model back into `{"VariantName": payload}`)
- raw payload fallback for unknown sentinel construction
- `Reply` Ok/Err unwrapping helper

Generated modules own:
- Pydantic model declarations with validators/serializers
- per-surface typed parse/serialize entrypoints (e.g., `parse_request(data: dict) -> Request`)
- wire-name-to-variant-class mappings (generated dicts)

Runtime owns:
- frame I/O and buffering
- invoking type decode/encode at the right points
- mapping `ValidationError` into the runtime error taxonomy

## 17. Configuration and Socket Discovery Policy

`config.py` owns:
- socket path resolution
- timeout defaults and overrides
- framing limits
- event buffering limits

Socket path discovery precedence:
1. Explicit constructor/config argument.
2. `NIRI_SOCKET` environment variable.
3. No further fallback — if neither is available, raise `ConfigError`.

Timeout config:
- connect timeout (default: 5s)
- request timeout (default: 10s)
- event read timeout (default: `None` — block indefinitely, with per-call override)

Framing/backpressure config:
- max frame size (default: 4 MiB)
- event queue capacity (default: 256)

## 18. Runtime and Transport Design

Core concerns:
1. Unix socket connection establishment via `asyncio.open_unix_connection()`
2. Newline-delimited frame parsing (read until `\n`)
3. Bounded buffering and max-frame enforcement
4. Timeout and cancellation via `asyncio.timeout()` / `asyncio.wait_for()`
5. Idempotent close
6. Deterministic settlement of in-flight operations
7. Command and event connections are independent (separate socket connections to the same path)

Command connection model:
- Niri uses a one-request-per-connection model for commands: connect, send request, read response, close.
- The client may open a new connection for each command, or the API may pool/reuse if niri supports it. Start with one-connection-per-request to match upstream `niri msg` behavior.

Event connection model:
- Client connects, sends `{"EventStream":[]}` (or the appropriate request), then reads newline-delimited events indefinitely.
- Connection stays open for the lifetime of the event subscription.

Lifecycle states:
- `init`
- `connecting`
- `ready`
- `closing`
- `closed`

Invariants:
1. `close()` is idempotent.
2. New operations rejected once closing starts.
3. In-flight operations settle deterministically (cancel or drain).
4. No post-closed response/event emission.

## 19. Concurrency and Task-Safety Contract

1. For the command client, if using one-connection-per-request, concurrent `request()` calls are naturally safe (each gets its own socket). If a shared connection model is used, serialization of requests is the client's responsibility.
2. `close()` may be called from a different task; it transitions to `closing` and settles in-flight work deterministically.
3. Event stream consumer model is single-consumer per stream instance.
4. Multiple consumers require explicit fan-out implemented by caller or separate stream instances.
5. Shared client objects across tasks are supported only within defined request/close semantics; undefined concurrent mutation is forbidden.

## 20. Event Stream Delivery and Backpressure Policy

1. Event ordering is preserved as received from wire.
2. Buffering is bounded by configured queue capacity (default 256).
3. Overflow behavior is configurable. Default: drop-oldest with a warning log. Optional strict mode: fail-fast by raising a backpressure error and closing the stream.
4. No silent event drop — both modes surface overflow visibility (log warning or exception).
5. API supports `async for event in stream` (async iterator) and explicit `await stream.next(timeout=...)` forms.
6. Cancellation during await read exits predictably and preserves lifecycle invariants.

## 21. Version-Mismatch Compatibility Policy

Because `niri-pypc` is pinned, mismatch behavior is explicit:

1. After connecting, the client can optionally send a `Version` request and compare the compositor's reported niri version against the pinned `niri-ipc 25.11` expectations. This is a post-connect check, not a wire-level handshake (niri's IPC has no handshake).
2. If a hard mismatch is detected and policy is strict mode (default), fail fast with a compatibility error.
3. Optional relaxed mode may continue, but only with clear warning surface and unknown inbound sentinel handling active.
4. Outbound requests/actions always remain strict to pinned contract regardless of mode.

## 22. Reconnection Policy

Automatic reconnection is a non-goal for `niri-pypc`.

- `NiriClient` and `NiriEventStream` represent single socket lifetimes.
- If a connection drops, the caller is responsible for creating a new client/stream instance.
- The API should make it easy to reconnect (cheap construction, clear lifecycle), but will not implement retry loops, backoff, or automatic re-subscription internally.
- Downstream libraries like `niri-state` may implement reconnection policy on top.

## 23. Public API Concept

Client (command connection):

```python
async with NiriClient.connect(config) as client:
    version = await client.request(VersionRequest())
    outputs = await client.request(OutputsRequest())
```

Event stream:

```python
async with NiriEventStream.connect(config) as stream:
    async for event in stream:
        print(event)
```

Or with explicit next:

```python
async with NiriEventStream.connect(config) as stream:
    event = await stream.next(timeout=5.0)
```

Dual-channel convenience wrapper:

```python
async with NiriConnectionBundle.open(config) as bundle:
    version = await bundle.client.request(VersionRequest())
    async for event in bundle.events:
        print(event)
```

Bundle lifetime semantics:
- `NiriConnectionBundle.open()` establishes both command and event connections.
- Closing the bundle closes both connections.
- If the event stream connection drops, the command client remains usable (they are independent sockets). The bundle surfaces the event stream error but does not force-close the command client.
- If the command client encounters an error, the event stream remains open.
- The bundle provides convenience, not coupling — each member has independent lifetime within the bundle's overall scope.

Naming decision:
- Prefer `NiriConnectionBundle` over `NiriSession` to avoid state-store implications.
- This object coordinates sockets only; it does not maintain derived compositor state.

## 24. Error Taxonomy

Base exception:
- `NiriError` — base class for all niri-pypc errors.

Required categories (all subclass `NiriError`):
1. `TransportError` for socket/framing I/O failures.
2. `NiriTimeoutError` for connect/request/event timeouts (subclasses both `NiriError` and `TimeoutError`).
3. `DecodeError` for shape/validation failures during decode.
4. `ProtocolError` for wire-level contract violations.
5. `RemoteError` for error responses returned by the compositor (`"Err"` replies).
6. `LifecycleError` for invalid state transitions/usage.
7. `ConfigError` for invalid or unresolved configuration.
8. `InternalError` for impossible internal states (indicates a bug in niri-pypc).

Context fields should include (where applicable):
- operation name
- socket path
- lifecycle state
- retryability hint
- wrapped cause (`__cause__` via `raise ... from`)
- bounded raw payload excerpt when relevant

## 25. Testing Strategy

`tests/types/`:
- roundtrip encode/decode tests for all generated models
- golden fixture tests (known JSON -> model -> JSON)
- unknown variant sentinel behavior tests
- null/missing/optional field semantics
- metadata/provenance checks
- drift detection (regenerate and diff)

`tests/transport/`:
- partial/multi-frame reads
- oversize frame rejection
- malformed framing (missing newline, invalid JSON)
- disconnect mid-frame

`tests/api/`:
- request/response happy path (mock socket)
- timeout/cancellation/close behavior
- lifecycle state transitions

`tests/integration/`:
- mock socket server (asyncio unix socket server in-process)
- event sequencing and ordering
- decode failure paths
- command/event socket independence

`tests/live/`:
- gated by environment (`NIRI_SOCKET` must be set)
- version query and basic behavior checks
- skipped in CI by default

Explicit exclusion:
- reducer/selector/replay/convergence/state-store tests belong in `niri-state`, not `niri-pypc`.

## 26. CI Quality Gates

Required:
1. Schema export succeeds (requires Rust toolchain in CI).
2. IR normalization succeeds.
3. Type generation succeeds.
4. `verify-generated` passes with no diff.
5. Type test suite passes.
6. Transport/API/integration suites pass.
7. Lint (`ruff check`, `ruff format --check`) passes.
8. Type checking (`ty check`) passes.
9. Guardrails prevent manual edits in generated subtree and forbidden dependency directions.

Optional:
- live smoke tests where environment permits
- fixture hash verification
- decode-path benchmarks

## 27. Release and Versioning Policy

Release notes must include:
- `niri-pypc` version
- pinned `niri-ipc` version (`25.11`)
- schema/IR format changes
- generated artifact changes
- runtime API changes
- compatibility policy notes

Versioning follows standard Python package semantics (PEP 440). Upstream pin compatibility must always be explicit in release metadata.

## 28. Documentation Plan

Required docs:
1. High-level README
2. Generation workflow guide (how to re-export schema and regenerate types)
3. Contributor guide for pin updates
4. API examples for client and event stream usage
5. Generated vs hand-written boundary guide

README must explicitly state:
- pinned protocol alignment (niri-ipc 25.11)
- raw typed event delivery (not reduced state)
- dual-channel connection model
- recommendation to use `niri-state` for derived live compositor state

## 29. Implementation Phases

Phase A: Repository skeleton and pinned manifest.
- Create directory structure per Section 10.
- Write `schema/upstream-pin.toml` with version `25.11`.
- Add Rust toolchain to `devenv.nix`.
- Set `tool.uv.package = true` in `pyproject.toml` (required for editable installs).
- Scaffold empty `src/niri_pypc/` package with `__init__.py`.
- Exit criteria: `devenv shell` works, `uv sync --extra dev` succeeds, empty test suite runs.

Phase B: Schema export and IR normalization.
- Implement `tools/schema_exporter/` Rust binary.
- Add `export-schema` devenv script.
- Implement `tools/normalize_ir.py`.
- Run export, commit schema and IR artifacts.
- Exit criteria: `devenv shell -- export-schema` produces stable JSON Schema files; `normalize_ir.py` produces deterministic IR; re-running produces identical output.

Phase C: Deterministic Python type generation.
- Implement `tools/generate_types.py` reading IR and emitting Pydantic models.
- Generate all protocol types into `src/niri_pypc/types/generated/`.
- Generate `_metadata.py` with provenance info.
- Implement `tools/verify_generated.py` (regenerate to tempdir, diff against committed).
- Exit criteria: generation is byte-for-byte reproducible; verify passes.

Phase D: Type-layer tests and codec.
- Implement `types/codec.py` with externally-tagged enum helpers.
- Write roundtrip, golden fixture, unknown variant, and edge case tests.
- Exit criteria: full type test suite passes; all generated models encode/decode correctly.

Phase E: Transport/runtime implementation and tests.
- Implement `errors.py` with full error taxonomy.
- Implement `config.py` with socket discovery and defaults.
- Implement transport layer (framing, buffering, socket I/O).
- Write transport tests with mock sockets.
- Exit criteria: transport tests pass; framing edge cases covered.

Phase F: Client/event/bundle APIs and integration tests.
- Implement `NiriClient`, `NiriEventStream`, `NiriConnectionBundle`.
- Write API tests and integration tests with mock socket server.
- Write live tests (gated).
- Exit criteria: all test suites pass; public API matches Section 23 contract.

Exit criteria for each phase must be testable and enforced in CI.

## 30. Design Principles to Preserve

1. Protocol-first correctness over convenience.
2. Generated protocol contract, manual runtime semantics.
3. Reproducibility and deterministic generation.
4. Explicit lifecycle and error behavior.
5. No hidden magic around dual-channel semantics.
6. Clear layering: `niri-pypc` substrate, `niri-state` state engine.
7. Maximize Pydantic-native features; minimize custom serialization.
8. No automatic reconnection or implicit retry.

## 31. Final Recommendation

Build `niri-pypc` as a narrow, strict, pinned protocol/runtime library with deterministic generated types and hand-written socket/runtime behavior.

Pin to `niri-ipc 25.11`. Export schema via `schemars` JSON Schema support. Normalize to IR. Generate Pydantic v2 models. Hand-write transport and API layers.

Keep event delivery typed and raw, keep state derivation out of scope, and formalize `niri-state` as the downstream state layer.

That structure maximizes correctness, maintainability, reviewability, and long-term composability.
