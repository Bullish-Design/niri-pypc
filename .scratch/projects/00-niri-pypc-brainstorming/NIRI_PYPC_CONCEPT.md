# NIRI_PYPC_CONCEPT

## Authority and Scope
This document is the guiding concept for **`niri-pypc`**.

`niri-pypc` is a new Python library for the Niri IPC protocol, designed around two principles:
1. **Pinned upstream protocol alignment** with a specific `niri-ipc` Rust crate version.
2. **Strict separation of generated protocol types from hand-written runtime behavior**.

`niri-pypc` will live in a **single repository** and be developed inside a **`devenv.sh`-managed environment**.

This concept assumes:
- protocol types are generated from a Rust-side schema export step,
- generated protocol code lives under a dedicated `src/types` path,
- Unix socket runtime behavior is hand-written Python,
- the repository provides reproducible scripts to regenerate protocol artifacts from the pinned upstream source.

---

## Project Identity
### Library name
- **Project name:** `niri-pypc`
- Suggested import root: `niri_pypc`

### Naming rationale
The name intentionally communicates:
- **Niri** as the protocol authority,
- **py** for Python,
- **pc** for protocol/client concerns.

---

## Core Goals
1. **Pinned upstream correctness**
   - The protocol surface must match one exact `niri-ipc` crate version.
   - Drift is detected and intentional.

2. **Clear internal boundaries**
   - Generated protocol types are isolated from transport/runtime/client logic.
   - Runtime behavior is not code-generated.

3. **High-confidence typing**
   - Requests, responses, events, actions, and domain models are represented as typed Pydantic models.
   - Encode/decode logic is deterministic and testable.

4. **Runtime correctness**
   - Unix socket lifecycle, framing, timeouts, cancellation, disconnect handling, and event-stream semantics are explicit and tested.

5. **Single-repo reproducibility**
   - The repo contains the upstream pin, schema generation workflow, generated artifacts, and tests.
   - `devenv.nix` is the canonical development entrypoint.

6. **Ergonomic Python usage**
   - The public API should feel Pythonic without hiding protocol realities such as dual sockets for commands and event streams.

---

## Non-Goals
1. Backward compatibility with any previous Nim or Python library.
2. Runtime abstraction over multiple async backends.
3. Automatic support for unpinned upstream Niri changes.
4. Code generation for transport/runtime/client lifecycle logic.
5. Embedding business-policy or UI-specific helpers unrelated to Niri IPC itself.

---

## Upstream Authority
The authoritative protocol source is:
- **Rust crate:** `niri-ipc = <PINNED_VERSION>`

Rules:
1. Upstream crate semantics are canonical for protocol structure.
2. The pinned version is explicit in-repo.
3. All generated protocol artifacts derive from that exact pin.
4. Any pin bump is a deliberate change with regenerated code and test updates.
5. Release notes must state the exact upstream `niri-ipc` version.

---

## High-Level Architecture
`niri-pypc` is organized into two major concerns inside one repo:

### 1. Generated protocol types
These represent the pinned Niri IPC protocol surface.

Responsibilities:
- Pydantic models for protocol objects
- request/action/response/event types
- encode/decode helpers at the schema/type level
- generated wire-name maps and tagged-union adapters
- golden tests against fixtures and schema expectations

These should live under a dedicated path, conceptually:
- `src/niri_pypc/types/...`

### 2. Hand-written runtime/client code
These implement actual usage behavior.

Responsibilities:
- Unix socket connection management
- line-based framing and buffering
- timeout and cancellation semantics
- command request/response API
- event-stream subscription API
- optional dual-socket session coordination
- runtime error taxonomy and lifecycle state handling

These should live under paths such as:
- `src/niri_pypc/runtime/...`
- `src/niri_pypc/transport/...`
- `src/niri_pypc/api/...`
- `src/niri_pypc/errors.py`

The critical rule is:
- **generated protocol code describes the wire contract**
- **hand-written runtime code implements behavior over that contract**

---

## Why `src/types` Matters
The dedicated `src/types` area is not just a convenience. It is a correctness boundary.

Benefits:
1. Generated files are easy to identify.
2. Generated code can be tested exhaustively without mixing in socket behavior.
3. Regeneration workflows are simpler and safer.
4. Manual edits can be prohibited or clearly discouraged in generated sections.
5. Runtime code can depend on types without circular design pressure.

Recommended rule:
- Anything under `src/niri_pypc/types/generated/` is treated as authoritative generated output.
- Hand-authored type conveniences, adapters, or facades should live alongside but outside the generated subtree.

Example:
- `src/niri_pypc/types/generated/models.py`
- `src/niri_pypc/types/generated/actions.py`
- `src/niri_pypc/types/generated/requests.py`
- `src/niri_pypc/types/generated/responses.py`
- `src/niri_pypc/types/generated/events.py`
- `src/niri_pypc/types/__init__.py`
- `src/niri_pypc/types/codec.py`
- `src/niri_pypc/types/helpers.py`

---

## Proposed Repository Layout

```text
niri-pypc/
├─ devenv.nix
├─ devenv.yaml
├─ pyproject.toml
├─ README.md
├─ CHANGELOG.md
├─ .gitignore
├─ tools/
│  ├─ schema_exporter/
│  │  ├─ Cargo.toml
│  │  └─ src/main.rs
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
│     │     ├─ __init__.py
│     │     ├─ models.py
│     │     ├─ actions.py
│     │     ├─ requests.py
│     │     ├─ responses.py
│     │     ├─ events.py
│     │     └─ metadata.py
│     ├─ transport/
│     │  ├─ __init__.py
│     │  ├─ unix_socket.py
│     │  └─ framing.py
│     ├─ runtime/
│     │  ├─ __init__.py
│     │  ├─ timeouts.py
│     │  ├─ cancellation.py
│     │  └─ lifecycle.py
│     └─ api/
│        ├─ __init__.py
│        ├─ client.py
│        ├─ event_stream.py
│        └─ session.py
└─ tests/
   ├─ types/
   ├─ transport/
   ├─ api/
   ├─ integration/
   ├─ live/
   └─ fixtures/
```

---

## Development Environment Strategy
`devenv.sh` is the canonical shell for all development workflows.

The development environment should pin and provide:
- Python toolchain
- Rust toolchain
- Cargo
- testing tools
- lint/format tooling
- any auxiliary JSON/schema tooling required by generation scripts

The environment must support a fully reproducible sequence:
1. enter devenv shell,
2. export schema from pinned Rust crate,
3. generate Python types,
4. run verification checks,
5. run the full test suite.

### `devenv.nix` responsibilities
`devenv.nix` should expose scripts such as:
- `generate-schema`
- `generate-types`
- `verify-generated`
- `test-types`
- `test-runtime`
- `test-all`

### Suggested script behavior
#### `generate-schema`
Runs the Rust schema exporter using the pinned upstream crate version and writes canonical artifacts to `schema/exported/`.

#### `generate-types`
Consumes exported schema/IR and rewrites the generated Python protocol files under `src/niri_pypc/types/generated/`.

#### `verify-generated`
Fails if generated files differ from what the current pinned schema should produce.

#### `test-types`
Runs the schema/type/golden tests only.

#### `test-runtime`
Runs transport and client behavior tests.

#### `test-all`
Runs the entire quality gate sequence.

---

## Upstream Pin and Schema Export Workflow
The protocol synchronization workflow is the center of the project.

### Pinned manifest
Add a small pinned manifest file, for example:

```toml
[niri_ipc]
crate = "niri-ipc"
version = "<PINNED_VERSION>"
```

Recommended location:
- `schema/upstream-pin.toml`

### Rust exporter tool
The repo should contain a tiny Rust utility whose only job is to:
1. depend on `niri-ipc = =<PINNED_VERSION>`
2. enable the required upstream schema feature(s)
3. emit a machine-readable artifact for the protocol surface
4. normalize output so the Python generator sees stable input

### Export artifacts
Keep exported artifacts in-repo for reproducibility and reviewability.

Recommended outputs:
- `schema/exported/niri-ipc-schema.json`
- `schema/exported/niri-ipc-ir.json`

Where:
- **schema JSON** is raw-ish exported protocol metadata
- **IR JSON** is a normalized intermediate representation tailored for Python generation

### Why IR is important
Direct code generation from raw schema is often awkward. A normalized IR makes generation deterministic and easier to evolve.

The IR should flatten or standardize:
- tagged-union structure
- enum names and wire names
- field nullability
- optional/default values
- list and map shapes
- unknown-variant policy hooks
- metadata such as source crate version and generation timestamp

---

## Generation Strategy
The generator should be deterministic and idempotent.

### Inputs
- pinned upstream manifest
- exported schema/IR artifacts
- generator templates or code emission logic

### Outputs
- generated protocol modules
- generated metadata file
- optionally generated fixture manifests or baseline tests

### Required generated modules
1. `models.py`
2. `actions.py`
3. `requests.py`
4. `responses.py`
5. `events.py`
6. `metadata.py`

### `metadata.py` should include
- pinned upstream crate name
- pinned upstream crate version
- generator version
- generation date or commit reference
- schema hash / IR hash

### Generation invariants
1. Same input produces byte-for-byte identical generated output.
2. Generated files contain clear headers such as:
   - “generated file; do not edit manually”
3. Manual code does not live in generated files.
4. The generator must fail loudly on unsupported shapes.

---

## Type System Design
The protocol layer should use **Pydantic models** consistently.

### Design priorities
1. Strong typing over loosely typed dicts
2. Explicit optionality
3. Stable tagged-union decoding
4. Clear roundtrip behavior for JSON encode/decode
5. Machine-friendly validation failures

### Protocol surfaces to model
#### Models
Domain objects such as:
- outputs
- workspaces
- windows
- layers
- keyboard layouts
- cast/session-like objects
- identifiers and references

#### Requests
Requests should reflect the exact wire contract and distinguish:
- unit requests
- struct payload requests
- nested action requests

#### Actions
Actions are large and benefit heavily from generation.

The generated action layer should include:
- action models
- wire-name mappings
- typed constructors where useful
- consistent encode behavior

#### Responses
Responses should support:
- handled/unit responses
- typed payload responses
- typed success/error boundaries where appropriate
- explicit unknown handling policy

#### Events
Events should support:
- typed variant decoding
- event payload models
- explicit handling for unknown or future-added variants based on project policy

---

## Unknown Variant Policy
This must be chosen once and enforced consistently.

Two viable strategies:

### Option A: strict failure
- Unknown request/response/event/action variants raise validation or decode failure.
- Best for strict pinned correctness.
- Most appropriate when exact protocol matching matters more than resilience.

### Option B: explicit unknown sentinels
- Unknown variants decode into typed `Unknown*` wrapper models carrying raw payload.
- Best for forward-observability and diagnostics.
- Slightly more complex but often friendlier operationally.

### Recommended policy
For `niri-pypc`, prefer:
- **strict outbound generation**
- **explicit unknown sentinels for inbound responses/events**

Rationale:
- requests/actions sent by the client should always match the pinned protocol,
- inbound payloads may contain additive change or environment mismatch information that is useful to preserve for debugging.

If this policy is adopted, it should be implemented uniformly across generated decode surfaces and verified by tests.

---

## Encoding and Decoding Boundaries
The type layer should own JSON shape correctness.

### Responsibilities of `types/codec.py`
- normalize JSON encode/decode helpers
- provide tagged-variant dispatch helpers
- define shared adapter behavior used by generated modules
- centralize raw JSON fallback logic if adopted

### Responsibilities of generated modules
- declare the models
- define per-surface adapters
- expose typed parse/serialize helpers

### Responsibilities of runtime code
- read and write newline-delimited frames
- invoke type-layer decode/encode functions
- map failures into runtime error types

---

## Public API Concept
The public Python API should expose a small, disciplined surface.

### Client API
Suggested concept:

```python
async with NiriClient.connect(config) as client:
    version = await client.request(VersionRequest())
    outputs = await client.request(OutputsRequest())
```

### Event stream API
Suggested concept:

```python
async with NiriEventStream.subscribe(config) as stream:
    event = await stream.next(timeout=5.0)
```

### Optional session API
Suggested concept:

```python
async with NiriSession.open(config) as session:
    version = await session.client.request(VersionRequest())
    event = await session.events.next(timeout=5.0)
```

### Important behavioral rule
The API should not pretend the protocol is single-channel if it is not.

The library should explicitly model:
- command socket
- event socket
- optional coordinated session abstraction over both

---

## Dependency Rules
Allowed dependency direction:

```text
api -> transport, runtime, types, errors
transport -> runtime, errors
runtime -> errors
types -> (internal type helpers only)
errors -> no internal deps
```

Forbidden couplings:
1. Generated `types/generated/*` must not import transport or API layers.
2. Transport code must not import API convenience wrappers.
3. Runtime lifecycle code must not depend on generated implementation details beyond public type helpers.
4. Public API conveniences must not duplicate encode/decode logic owned by the type layer.

---

## Runtime Design
Runtime code is hand-written and correctness-focused.

### Core runtime concerns
1. Unix socket connection establishment
2. newline frame parsing
3. bounded buffering and max-frame enforcement
4. timeouts and cancellation
5. idempotent close
6. dual-socket coordination
7. deterministic settlement of in-flight operations

### Lifecycle states
Each connection should have explicit states such as:
- `init`
- `connecting`
- `ready`
- `closing`
- `closed`

### Invariants
1. `close()` is idempotent.
2. No operations are accepted after closing starts.
3. In-flight operations settle deterministically.
4. No events or responses are emitted after closed.

---

## Error Model
Define a clear runtime error taxonomy.

Suggested categories:
1. `TransportError`
2. `TimeoutError`
3. `ProtocolError`
4. `DecodeError`
5. `LifecycleError`
6. `InternalInvariantError`

Suggested context fields:
- operation name
- socket path
- lifecycle state
- retryability hint
- wrapped cause
- raw snippet or bounded payload excerpt where relevant

The type layer may surface validation errors, but runtime code should map them into the public error model consistently.

---

## Testing Strategy
The test strategy should treat the generated types as a major surface area deserving their own rigorous suite.

## 1. Type-layer tests
Location:
- `tests/types/`

These validate the generated protocol models independently of sockets.

### Required categories
#### Roundtrip tests
- request encode/decode
- action encode/decode
- response decode/encode where meaningful
- event decode/encode where meaningful

#### Golden fixture tests
- known-good JSON fixtures from upstream or curated snapshots
- exact expected model parse results
- exact expected serialized output where appropriate

#### Unknown-variant tests
- verify the chosen unknown policy
- ensure strict/unknown behavior is consistent across responses and events

#### Optionality/nullability tests
- null vs missing vs empty collection semantics
- optional nested payload handling

#### Generated metadata tests
- pinned upstream version present
- schema hash present
- generator version present

#### Drift detection tests
- verify generated files align with the current exported schema

## 2. Transport tests
Location:
- `tests/transport/`

### Required categories
- partial frame reads
- multiple frames in one read
- oversize frame rejection
- malformed newline behavior
- disconnect mid-frame

## 3. API tests
Location:
- `tests/api/`

### Required categories
- request/response happy path
- event stream handshake
- timeout behavior
- cancellation behavior
- close-during-in-flight behavior
- repeated open/close loops

## 4. Integration tests
Location:
- `tests/integration/`

Use a mock Unix socket server to simulate Niri behavior.

### Required categories
- handled response for event stream subscription
- event sequencing
- protocol decode failures
- command and event socket independence

## 5. Live tests
Location:
- `tests/live/`

Gated by environment such as `NIRI_SOCKET`.

### Required categories
- version query
- small query suite
- event receipt during compositor activity

---

## CI Quality Gates
Required gates should include:
1. schema export runs successfully in devenv
2. type generation runs successfully in devenv
3. `verify-generated` passes with no diff
4. type test suite passes
5. transport test suite passes
6. API/integration suite passes
7. import/lint guard preventing accidental manual edits or forbidden dependency directions

Optional but valuable:
- smoke live test in a suitable environment
- fixture hash verification
- benchmark subset for hot decode paths

---

## Release Policy
Because the project is pinned to upstream protocol versions, releases should be explicit.

### Release notes should state
- `niri-pypc` version
- pinned `niri-ipc` upstream crate version
- whether the schema/export format changed
- whether generated artifacts changed
- any runtime API changes

### Versioning guidance
The project can use normal Python package versioning, but compatibility notes should always include the upstream protocol pin.

Example:
- `niri-pypc 0.3.0` — aligned to `niri-ipc 25.08.0`

---

## Documentation Plan
The repo should include:
1. high-level README
2. generation workflow guide
3. contributor guide for updating the upstream pin
4. examples for client and event stream usage
5. guidance on generated vs hand-written code boundaries

### README should clearly explain
- this library is pinned to a specific upstream Niri protocol version
- generated types are authoritative for the protocol surface
- runtime behavior is hand-written
- event streaming requires a separate connection model

---

## Recommended Immediate Implementation Plan
### Phase A: Repository skeleton
1. create repo layout
2. add `pyproject.toml`
3. add `devenv.nix` scripts
4. add pinned upstream manifest

Exit criteria:
- shell environment works
- scripts exist as stubs

### Phase B: Rust exporter
1. create minimal Rust schema exporter
2. pin `niri-ipc`
3. emit schema and normalized IR

Exit criteria:
- `generate-schema` writes deterministic artifacts

### Phase C: Python type generation
1. build `generate_types.py`
2. generate `src/niri_pypc/types/generated/*`
3. generate metadata and initial fixtures

Exit criteria:
- generated modules import successfully
- type-only tests begin passing

### Phase D: Type-layer test expansion
1. add exhaustive golden and roundtrip tests
2. finalize unknown-variant policy
3. add drift verification

Exit criteria:
- type test suite is thorough and stable

### Phase E: Runtime transport
1. implement Unix socket transport
2. implement frame parser
3. implement timeout/cancellation helpers

Exit criteria:
- transport tests pass

### Phase F: Client and event stream APIs
1. implement command client
2. implement event stream client
3. implement optional session coordination

Exit criteria:
- integration tests pass

---

## Design Principles to Preserve
1. **Protocol-first correctness before convenience**
2. **Generated protocol surface, manual runtime semantics**
3. **Pinned upstream reproducibility**
4. **Single-repo coherence**
5. **Strong type-layer testing**
6. **Explicit lifecycle and error behavior**
7. **No hidden magic around dual-socket event semantics**

---

## Summary Recommendation
`niri-pypc` should be a single-repo Python library with:
- a pinned upstream `niri-ipc` Rust crate version,
- a Rust-side schema exporter driven from `devenv.nix`,
- generated Pydantic protocol models under `src/niri_pypc/types/`,
- a dedicated, thorough type-layer test suite,
- and hand-written Unix socket/client/event-stream runtime code.

That structure gives the project the best balance of:
- correctness,
- maintainability,
- reviewability,
- reproducibility,
- and long-term protocol alignment.
