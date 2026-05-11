# niri-pypc Refactoring Guide

## Purpose

This guide is an implementation-grade refactoring plan for fixing the issues identified in the code review of `niri-pypc`.

It is written for a brand new intern. Follow it exactly, in order, without skipping ahead. The goal is not merely to “make tests pass.” The goal is to restore the library’s core promises:

- faithful protocol typing against the pinned upstream schema
- deterministic schema → IR → code generation
- clean separation between generated code and handwritten runtime code
- correct runtime behavior for command requests, event streams, lifecycle, timeouts, and shutdown
- meaningful tests that catch regressions in the areas that matter most

The target architecture is already defined by the project’s concept, spec, and implementation guide. This guide tells you how to get the implementation back into alignment with that target.

---

## Non-Negotiable Rules

1. **Do not hand-edit generated files to “fix” protocol types.**
   - Files under `src/niri_pypc/types/generated/` are outputs, not sources.
   - All protocol-shape fixes must happen in:
     - `tools/normalize_ir.py`
     - `tools/generate_types.py`
     - or, if absolutely necessary, in upstream schema export inputs

2. **Do not mix generated-layer fixes with runtime-layer fixes in one large unreviewable patch.**
   Work in phases and commit after each phase.

3. **Before changing behavior, add or improve tests that reproduce the broken behavior.**
   This is especially important for:
   - reply payload loss
   - event stream shutdown
   - queue-full behavior on close
   - `event_read_timeout` behavior
   - `verify_generated`

4. **Do not weaken types to make edge cases easier.**
   If a field is `list[str]`, the fix is to preserve that shape in IR and generation, not to widen it to `list[Any]`.

5. **Do not bypass lifecycle abstractions.**
   If a class uses `LifecycleManager`, all state changes must go through it.

6. **Keep the generated/manual boundary strict.**
   Generated code defines the wire contract. Handwritten code defines runtime behavior.

---

## What Is Broken

There are two top-level problem clusters.

### Cluster A: Protocol generation is lossy

Symptoms:
- arrays degrade to `list[Any]`
- tuple-like arrays degrade to `list[Any]`
- some nullable refs are classified incorrectly
- several reply payload models are generated as empty classes instead of newtypes
- `verify_generated` does not pass on the repo as delivered

Root cause:
- `tools/normalize_ir.py` is not preserving enough schema structure
- some variant classification logic is too shallow
- the generator then faithfully emits wrong code from wrong IR

### Cluster B: Runtime stream/lifecycle behavior is wrong

Symptoms:
- `close()` can raise `asyncio.QueueFull`
- event reader silently swallows malformed events
- reader-side connection failures collapse into generic stream-close behavior
- `event_read_timeout` can kill a stream prematurely
- `__anext__()` does not match async iteration contract
- lifecycle transitions are not used consistently
- `strict_version_check` is dead configuration

Root cause:
- the event stream currently uses a sentinel/queue model without a clear event-or-error channel
- close semantics were implemented incompletely
- lifecycle is only partially integrated

---

## Recommended Execution Order

Do the work in this exact order:

1. Establish a clean baseline and remove noise
2. Add failing regression tests for the known bugs
3. Fix `tools/normalize_ir.py`
4. Regenerate types and fix `tools/generate_types.py` only if needed
5. Make `verify_generated` pass
6. Strengthen type-level tests with high-value golden cases
7. Refactor the event stream shutdown/error model
8. Fix lifecycle and API consistency (`NiriClient`, `NiriConnectionBundle`)
9. Decide and implement the `strict_version_check` policy
10. Clean repo hygiene and tighten CI expectations
11. Run the full verification sequence

Do **not** start with event stream cleanup before the generation pipeline is fixed. The type layer is the foundation.

---

## Phase 0: Prepare the Workspace

### Goal
Get to a state where every later failure is meaningful.

### Files to inspect
- `pyproject.toml`
- `devenv.nix`
- `.gitignore` or equivalent ignore config
- repository root for committed caches/build outputs

### Tasks
1. Create a branch dedicated to this refactor.
2. Remove committed junk from the working tree if present:
   - `__pycache__/`
   - `*.pyc`
   - `tools/schema_exporter/target/`
3. Add ignore rules if they are missing.
4. Confirm the project installs and the test suite can be run locally.

### Commands
```bash
uv sync --extra dev
PYTHONPATH=src pytest -q
python tools/verify_generated.py --ir schema/ir/niri-ipc-ir.json --generated-dir src/niri_pypc/types/generated/
```

### Done when
- the repo has no committed cache/build artifacts left in tracked files
- tests run locally
- `verify_generated` status is known and reproducible

### Pitfalls
- Do not combine this cleanup with behavioral code changes.
- Keep this as a separate commit if possible.

---

## Phase 1: Add Regression Tests Before Fixing Code

### Goal
Lock in the known failures so you can prove they are fixed.

### New tests to add
Create or extend these files:
- `tests/types/test_golden.py` **(new)**
- `tests/types/test_roundtrip.py`
- `tests/api/test_event_stream.py`
- optionally `tests/integration/test_event_flow.py`

### 1A. Reply payload fidelity tests

Add tests for these reply variants:
- `FocusedOutput`
- `FocusedWindow`
- `Outputs`
- `PickedColor`
- `PickedWindow`
- `Layers`
- `Windows`
- `Workspaces`

#### What to test
For each one:
1. parse a realistic raw `{"Ok": {"VariantName": payload}}`
2. validate through `Reply.model_validate(...)`
3. unwrap via `unwrap_reply(...)` if the test is at codec/client level
4. assert the resulting payload model contains the expected typed structure
5. serialize back and assert the original payload survives roundtrip

#### Example pattern
```python
def test_outputs_reply_preserves_payload():
    raw = {
        "Ok": {
            "Outputs": [
                {
                    "name": "DP-1",
                    "make": "Example",
                    "model": "Display",
                    "is_custom_mode": False,
                    "modes": [
                        {
                            "width": 2560,
                            "height": 1440,
                            "refresh_rate": 144000,
                            "is_preferred": True,
                        }
                    ],
                    "current_mode": 0,
                    "logical": None,
                    "physical_size": [600, 340],
                    "serial": None,
                    "vrr_enabled": False,
                    "vrr_supported": True,
                }
            ]
        }
    }

    reply = Reply.model_validate(raw)
    result = unwrap_reply(reply)
    assert len(result.payload) == 1  # or assert exact type based on final unwrap policy
    dumped = reply.model_dump(mode="json")
    assert dumped == raw
```

### 1B. Generator-shape tests

Add tests that directly assert generated types are not widened unnecessarily.

#### Cases to assert
- `SpawnAction.command` is `list[str]`
- `Output.modes` is `list[Mode]`
- `PickedColor.rgb` is a concrete numeric tuple/list shape if represented that way by the schema strategy
- `WindowLayout.tile_size` is not `list[Any]`
- `WindowLayout.window_offset_in_tile` is not `list[Any]`

Use either:
- `model_fields[field_name].annotation`
- or a structural roundtrip test with concrete sample data

### 1C. Event-stream close behavior tests

Add these tests:

#### `test_close_with_full_queue_does_not_raise`
Setup:
- `event_queue_capacity=1`
- ensure one event is already queued
- call `await stream.close()`
- assert no exception

#### `test_transport_error_surfaces_from_next`
Setup:
- start stream
- make mock server close connection unexpectedly
- next consumer call should raise `TransportError`, not `LifecycleError`

#### `test_event_read_timeout_does_not_autoclose_stream`
Setup:
- configure `event_read_timeout=0.01`
- delay server event for longer than that
- if the new design treats `event_read_timeout` as consumer timeout only, assert the stream remains open until caller timeout or event arrival

#### `test_async_iteration_stops_cleanly`
Setup:
- close the stream
- assert async iteration terminates with `StopAsyncIteration`

### Done when
- these tests fail against the current broken implementation
- each failure clearly points to a real issue, not flaky timing

### Pitfalls
- Avoid writing tests that assert current buggy behavior.
- Avoid overly synthetic payloads that hide typing issues.

---

## Phase 2: Fix `tools/normalize_ir.py`

### Goal
Produce a lossless-enough IR for the pinned schema shapes actually used by `niri-ipc`.

### Files to change
- `tools/normalize_ir.py`

### Main design problem
`canonical_type()` returns too early. It checks `type` first, so structured array/map schemas are flattened before their inner shape is inspected.

### Refactoring plan

#### 2A. Rewrite `canonical_type()` as a shape-first classifier
Current order is wrong. Replace it with this conceptual order:

1. nullable union / optional wrapper
2. `$ref`
3. arrays
4. maps / `additionalProperties`
5. objects with fields
6. primitive fallback

#### Recommended logic
```python
def canonical_type(schema: dict, defs: dict) -> str:
    # 1. Optional forms
    if is_optional_schema(schema):
        inner = strip_optional(schema)
        return f"option<{canonical_type(inner, defs)}>"

    # 2. Direct ref
    if "$ref" in schema:
        return f"ref:{resolve_ref(schema['$ref'])}"

    # 3. Array forms
    if schema.get("type") == "array" or "items" in schema:
        return canonical_array_type(schema, defs)

    # 4. Map forms
    if schema.get("type") == "object" and "additionalProperties" in schema:
        value_type = canonical_type(schema["additionalProperties"], defs)
        return f"map<string,{value_type}>"

    # 5. Plain object-with-properties
    if schema.get("type") == "object" and "properties" in schema:
        return "object"

    # 6. Primitive
    return primitive_type_from_schema(schema)
```

### 2B. Add helper functions
Add small helper functions instead of one monolith:
- `is_optional_schema(schema: dict) -> bool`
- `strip_optional(schema: dict) -> dict`
- `canonical_array_type(schema: dict, defs: dict) -> str`
- `primitive_type_from_schema(schema: dict) -> str`

This will make the file easier to reason about and test.

### 2C. Properly support optional forms
You need to support both of these patterns:
- `{"type": ["null", "string"]}`
- `{"anyOf": [{"$ref": ...}, {"type": "null"}]}`

The optional detector should not assume the non-null branch is primitive. It must preserve refs, arrays, maps, and nested options correctly.

### 2D. Properly support arrays
For array schemas, preserve the item type:
- `{"type": "array", "items": {"type": "string"}}` → `array<string>`
- `{"type": "array", "items": {"$ref": "#/$defs/Mode"}}` → `array<ref:Mode>`
- `{"type": "array", "items": {"anyOf": [...]}}` → nested normalized type

If the upstream schema uses fixed-length tuple arrays (`prefixItems` or equivalent), decide on one deterministic representation and document it.

### Recommendation for tuple-like arrays
Do **not** invent a new IR type unless necessary. Prefer one of these two approaches:

#### Option A: keep current IR version and represent tuples as `array<integer>` / `array<float>`
Use this if tuple element types are homogeneous and the main problem is losing the element type.

#### Option B: bump `ir_version` and introduce `tuple<T1,T2,...>`
Use this only if the schema actually requires heterogeneous tuples and the current IR cannot represent them faithfully.

For an intern-safe implementation, choose **Option A unless the real schema forces Option B**.

### 2E. Properly support maps
For `additionalProperties`, preserve the value type:
- `{"type": "object", "additionalProperties": {"$ref": ...}}` → `map<string,ref:...>`

### 2F. Fix enum variant classification
`classify_variants()` must correctly distinguish:
- unit variants
- newtype variants
- struct variants

#### Specific bug to fix
A payload like:
```json
{"FocusedOutput": {"anyOf": [{"$ref": "#/$defs/Output"}, {"type": "null"}]}}
```
should become a **newtype** with inner type `option<ref:Output>`, not an empty struct.

#### Recommended classification rule
For each variant payload:
1. If it is a plain object with meaningful `properties`, classify as `struct`
2. Otherwise, compute `inner = canonical_type(payload_schema, defs)`
3. If `inner == "object"` and there are no fields, decide explicitly whether this is truly an empty struct or an unsupported ambiguous case
4. In all normal scalar/ref/array/option cases, classify as `newtype`

### 2G. Add focused tests for the normalizer itself
Create a new file:
- `tests/types/test_ir_normalization.py` **(new)**

Add fixture-sized unit tests for:
- `array<string>`
- `array<ref:Mode>`
- `option<ref:Output>` from `anyOf`
- `map<string,ref:Workspace>`
- unit variant classification
- struct variant classification
- newtype variant classification for optional refs

### Done when
- the normalizer emits concrete IR for the previously degraded shapes
- targeted normalization tests pass
- rerunning the tool is byte-identical

### Pitfalls
- Do not silently “default to string” for unsupported shapes.
- Hard-fail on shapes you truly do not understand.
- Avoid broad fallback branches that hide classification mistakes.

---

## Phase 3: Regenerate Types and Repair the Generator Only If Needed

### Goal
Once IR is correct, ensure generated Python models reflect it exactly.

### Files to inspect or change
- `tools/generate_types.py`
- `src/niri_pypc/types/generated/*` via regeneration only

### Procedure
1. Run the normalizer.
2. Regenerate all types.
3. Inspect the generated diffs before changing the generator.

### Commands
```bash
python tools/normalize_ir.py --schema-dir schema/exported --output schema/ir/niri-ipc-ir.json --upstream-pin schema/upstream-pin.toml
python tools/generate_types.py --ir schema/ir/niri-ipc-ir.json --output-dir src/niri_pypc/types/generated
```

### What to inspect first
Check whether these classes are now correct without touching the generator:
- `SpawnAction`
- `Output`
- `WindowLayout`
- `FocusedOutputResponse`
- `FocusedWindowResponse`
- `OutputsResponse`
- `PickedColorResponse`
- `PickedWindowResponse`
- `LayersResponse`
- `WindowsResponse`
- `WorkspacesResponse`

### If the generator still needs changes
Only change it if the new IR is correct but emitted code is still wrong.

#### Generator areas to validate
1. `ir_type_to_python()`
   - ensure `array<T>` maps to `list[T]`
   - ensure `map<string,T>` maps to `dict[str, T]`
   - ensure nested option/array/ref combinations preserve structure

2. Newtype generation
   - if variant `kind == "newtype"`, emit `payload: <python_type>`
   - do not convert optional refs into empty classes

3. Imports
   - ensure generated modules import `Any` only when actually needed
   - ensure referenced model names are imported or available by forward reference

4. Metadata / headers
   - preserve determinism
   - do not add timestamps or environment-specific values

### Add a generator-level regression test
Create:
- `tests/types/test_generated_shapes.py` **(new)**

This should assert concrete annotations for several key fields/classes in the generated modules.

### Done when
- regenerated types now express the expected payloads and field types
- no manual edits were made inside `src/niri_pypc/types/generated/`
- generator tests pass

### Pitfalls
- Do not “patch” one broken generated file manually.
- If one generated class is wrong, fix the pipeline.

---

## Phase 4: Make `verify_generated` a Hard Green Gate

### Goal
Restore trust that committed generated code matches the current generator + IR.

### Files to inspect
- `tools/verify_generated.py`

### Tasks
1. Run `verify_generated` after regeneration.
2. If it still fails, inspect whether the issue is:
   - nondeterministic output order
   - newline/formatting mismatch
   - missing file generation
   - stale generated tree
3. Fix determinism at the source.

### Determinism checklist
- top-level types sorted
- variants sorted
- fields sorted
- file write order stable
- exported names stable
- no set iteration without sorting
- no dependence on insertion order from unsorted upstream dict traversal

### Done when
```bash
python tools/verify_generated.py --ir schema/ir/niri-ipc-ir.json --generated-dir src/niri_pypc/types/generated
```
exits 0 and prints the expected success message.

### Pitfalls
- Do not accept “verify-generated is flaky.” It must not be flaky.

---

## Phase 5: Strengthen the Codec and Reply Handling

### Goal
Make the codec layer explicit, durable, and not dependent on fragile naming conventions.

### Files to change
- `src/niri_pypc/types/codec.py`
- possibly small generator changes if reply handling benefits from stronger generated metadata

### Current problem areas
- encode-side failures should not raise decode-oriented exceptions
- reply unwrapping should not infer semantics from class name prefixes
- error messages should be precise and contextual

### Recommended changes

#### 5A. Introduce `EncodeError`
The spec mentions encode failures as a distinct concern. Add:
```python
class EncodeError(NiriError):
    """Serialization failure for outbound protocol values."""
```

If you prefer not to extend the public taxonomy, use `ProtocolError` for encode-side mapping failures. `DecodeError` is the wrong class.

#### 5B. Make `encode_externally_tagged()` structural
Current rule should be explicit:
- 0 fields → unit variant → return string wire name
- exactly 1 field named `payload` → newtype variant → return `{wire_name: payload}`
- otherwise → struct variant → return `{wire_name: dumped_dict}`

Do not rely on comments or assumptions. Implement exactly this.

#### 5C. Make `unwrap_reply()` structural
Do not use class-name heuristics such as “starts with `Ok`” or “starts with `Err`”.

Recommended approach:
1. Expect a `Reply` root model whose `variant` is one of two generated reply envelope models
2. Inspect the actual generated type or generated wire-name mapping
3. If variant is `Err`, raise `RemoteError`
4. If variant is `Ok`, return its payload exactly

If needed, improve the generator so the reply envelope models are easy to distinguish structurally.

### Tests to add or update
- `tests/types/test_roundtrip.py`
- `tests/types/test_unknown_variants.py`
- new codec-focused tests if useful

Cases:
- unit encode/decode
- newtype encode/decode
- struct encode/decode
- unknown inbound reply/event sentinel behavior
- `unwrap_reply()` happy path and error path
- encode-side invalid variant raises correct exception class

### Done when
- codec behavior is fully structural
- reply handling does not depend on class-name strings
- tests cover unit/newtype/struct cases explicitly

---

## Phase 6: Refactor `NiriEventStream` Around an Explicit Queue Item Model

### Goal
Fix shutdown, error propagation, async iteration, and backpressure semantics.

### Files to change
- `src/niri_pypc/api/event_stream.py`
- possibly `src/niri_pypc/errors.py`
- tests under `tests/api/` and `tests/integration/`

### Main design change
Replace the current `BaseModel | _StreamClosed` queue item approach with an explicit internal item type.

### Recommended internal design
Define a small internal dataclass or tagged structure:
```python
@dataclass(slots=True)
class _EventItem:
    event: BaseModel

@dataclass(slots=True)
class _ErrorItem:
    error: Exception

@dataclass(slots=True)
class _ClosedItem:
    pass
```

Queue type becomes:
```python
asyncio.Queue[_EventItem | _ErrorItem | _ClosedItem]
```

This is much better than overloading a sentinel exception type.

### 6A. Reader task behavior
Refactor `_run_reader()` to do exactly this:

1. loop reading frames from the connection
2. on successful frame read:
   - decode JSON via `decode_frame`
   - validate as `Event`
   - enqueue `_EventItem(event.variant)`
3. on decode failure:
   - choose one policy and document it

### Recommended decode-failure policy
Treat malformed inbound events as **fatal protocol/decode failure** for the stream.

Reason:
- silent skipping hides real wire incompatibilities
- the design emphasizes explicit failures, not magical tolerance

So:
- if `decode_frame` or `Event.model_validate` fails, enqueue `_ErrorItem(error)` and close the stream

4. on transport failure:
   - enqueue `_ErrorItem(transport_error)`
   - close the stream
5. on cancellation:
   - exit cleanly without manufacturing an error
6. on natural close:
   - enqueue `_ClosedItem`

### 6B. Safe queue insertion helpers
Add helper methods:
- `_put_queue_item(item)`
- `_replace_oldest_and_put(item)`
- `_signal_close_nonblocking()`

These helpers must safely handle `QueueFull`.

#### Required behavior on close
A stream close must **never** fail because the queue is full.

Recommended approach:
- if inserting `_ClosedItem` or `_ErrorItem` into a full queue:
  - remove oldest item first
  - then insert close/error marker

This is consistent with “stream state beats stale queued events.”

### 6C. Separate consumer timeout from socket idle timeout
This is critical.

#### Recommended rule
- `next(timeout=...)` controls how long the **consumer** waits for the next queued item
- the reader task should usually read with `timeout=None` and allow the socket to remain idle indefinitely

The config field `event_read_timeout` is currently dangerous because it is used in the background reader. You have two viable choices:

##### Preferred option: reinterpret it as default consumer timeout
- leave the config field in place for compatibility
- use it only as the default for `next(timeout=None)`
- do **not** pass it to `conn.read_frame()` in the background reader

This is the safest fix and aligns with predictable stream behavior.

##### Alternative option: rename behavior and migrate
Only do this if you want to change the public API and are willing to update docs/spec. For this refactor, use the preferred option.

### 6D. `next()` behavior
`next()` should:
1. fail fast if stream is terminal and there is no queued terminal item left
2. await the queue with the caller timeout or default consumer timeout
3. dispatch based on queue item type:
   - `_EventItem` → return event
   - `_ErrorItem` → raise the stored exception
   - `_ClosedItem` → raise `LifecycleError` or a dedicated stream-closed error

### Recommendation
For direct `next()`, keep `LifecycleError` on closed stream if that is the chosen API contract.

### 6E. `__anext__()` behavior
`__anext__()` must convert closure into `StopAsyncIteration`.

Recommended pattern:
```python
async def __anext__(self) -> BaseModel:
    try:
        return await self.next()
    except LifecycleError as exc:
        raise StopAsyncIteration from exc
```

If `next()` raises `TransportError` or `DecodeError`, allow those to propagate. Async iteration should stop cleanly on deliberate closure, not on genuine failure.

### 6F. `close()` behavior
Implement `close()` in this order:
1. if already terminal, return
2. transition to `CLOSING`
3. cancel reader task
4. await reader task and swallow only cancellation expected from this shutdown path
5. close the connection if present
6. clear/drain queue as needed and insert one `_ClosedItem`
7. transition to `CLOSED`

### 6G. `_close_from_reader()` behavior
This helper must:
- not bypass actual socket close unless shutdown ordering guarantees reader owns the close path
- not crash if queue is full
- not insert multiple terminal items repeatedly

Add an internal idempotence guard if helpful, such as `_terminal_item_emitted: bool`.

### Tests to add/update
- `test_close_with_full_queue_does_not_raise`
- `test_transport_error_surfaces_from_next`
- `test_decode_error_surfaces_from_next`
- `test_event_read_timeout_only_affects_next_wait`
- `test_async_iteration_stops_on_closed_stream`
- `test_fail_fast_backpressure_emits_error`
- `test_drop_oldest_backpressure_replaces_oldest_event`

### Done when
- close is idempotent and never fails due to queue fullness
- connection loss surfaces as `TransportError`
- malformed event payloads surface as decode/protocol errors, not silent skips
- idle streams stay open until explicitly closed or disconnected
- async iteration ends cleanly on closure

### Pitfalls
- Do not swallow all exceptions in `_run_reader()`.
- Do not close the stream by only nulling the connection reference.

---

## Phase 7: Fix Lifecycle Integration in `NiriClient` and `NiriConnectionBundle`

### Goal
Make lifecycle usage honest and consistent.

### Files to change
- `src/niri_pypc/api/client.py`
- `src/niri_pypc/api/bundle.py`
- maybe `src/niri_pypc/runtime/lifecycle.py` only if absolutely necessary

### 7A. `NiriClient.connect()` should match the chosen contract
The spec describes `connect()` as async. The implementation currently makes it synchronous.

### Recommended fix
Make `NiriClient.connect()` async to match the public contract, even if it only validates config and returns quickly.

```python
@classmethod
async def connect(cls, config: NiriConfig | None = None) -> NiriClient:
    ...
```

This keeps the API surface aligned with the documented usage.

### 7B. Use lifecycle transitions consistently in `NiriClient`
Suggested behavior:
- constructor starts in `INIT`
- `connect()` transitions `INIT -> READY` after config validation
- `close()` transitions `READY -> CLOSING -> CLOSED` or directly to `CLOSED` if you keep the current close policy

Because `NiriClient` does not maintain a persistent socket, its lifecycle is mostly “usable vs closed.” That is fine, but it still should not leave the manager in `INIT` forever.

### 7C. Never mutate lifecycle private state directly
In `NiriConnectionBundle.__init__`, remove:
```python
self._lifecycle._state = LifecycleState.READY
```

Replace with a real transition or simplify bundle lifecycle.

### Recommendation for bundle
You have two good options:

#### Option A: keep lifecycle manager in bundle
- create manager in `INIT`
- in `open()`, after both members are ready, transition to `READY`
- in `close()`, transition `READY -> CLOSING -> CLOSED`

#### Option B: remove bundle lifecycle entirely
The bundle is just a convenience wrapper over two members that already manage their own lifecycle.

For this refactor, choose **Option A** if you want consistency with the existing design. Choose **Option B** only if bundle lifecycle provides no real value.

### 7D. Fix `NiriConnectionBundle.open()` to await client connect
If `NiriClient.connect()` becomes async, update:
```python
client = await NiriClient.connect(config)
```

### Tests to add/update
- `tests/api/test_client.py`
- `tests/api/test_bundle.py`
- `tests/api/test_lifecycle.py`

Cases:
- closed client rejects requests with `LifecycleError`
- bundle open/close transitions are valid
- bundle does not mutate lifecycle internals directly
- event stream failure does not make the client unusable
- client failure does not auto-close the event stream

### Done when
- no public class mutates `LifecycleManager._state` directly
- documented async/sync contracts match implementation
- lifecycle tests reflect real allowed transitions

### Pitfalls
- Do not overcomplicate client lifecycle for a non-persistent connection model.
- Simplicity is good, but cheating the abstraction is not.

---

## Phase 8: Decide the Fate of `strict_version_check`

### Goal
Remove dead configuration. Either implement the feature or remove the knob.

### Files to inspect/change
- `src/niri_pypc/config.py`
- `src/niri_pypc/api/client.py`
- maybe a new compatibility helper module if desired
- README/docs if public behavior changes

### Recommended choice
**Implement it**, because the concept explicitly includes version-mismatch policy and the config field already exists.

### Minimal implementation strategy
Add an opt-in compatibility check after client creation or before first command request.

#### Simpler implementation
Implement a helper method on `NiriClient`:
```python
async def check_version_compatibility(self) -> None:
    ...
```

This method:
1. sends `VersionRequest()`
2. compares returned compositor version against pinned expectation policy
3. if `strict_version_check` is true and mismatch is incompatible, raises a dedicated error

### Important note
The concept discusses comparing compositor-reported version against expectations, but there is no wire-level handshake. Keep this as an explicit API-side check, not implicit magic deep inside transport.

### What error to raise
Add a new public error if needed:
```python
class CompatibilityError(NiriError):
    ...
```

If you do not want to extend taxonomy, use `ProtocolError` with clear messaging. A dedicated `CompatibilityError` is cleaner.

### Alternative acceptable choice
If this is too much scope for the current refactor, remove `strict_version_check` from `NiriConfig` and document that compatibility checking is not yet implemented.

Do **not** keep a dead flag.

### Done when
- `strict_version_check` either has real behavior or no longer exists
- docs/config/tests reflect the real truth

---

## Phase 9: Tighten Error Taxonomy and Context

### Goal
Ensure errors carry the right meaning and enough debugging context.

### Files to change
- `src/niri_pypc/errors.py`
- callers that construct errors

### Tasks
1. Ensure all relevant errors include:
   - `operation`
   - `socket_path` where applicable
   - `state` for lifecycle errors
   - `retryable` where meaningful
2. Truncate `DecodeError.raw_payload` to 1024 chars max consistently
3. Use `raise ... from original_exception`
4. Add any missing error types chosen earlier (`EncodeError`, `CompatibilityError`)

### Tests
Add or update targeted tests for:
- `NiriTimeoutError` catchable as `TimeoutError`
- `DecodeError.raw_payload` truncation
- `RemoteError.remote_message`
- new error classes if added

### Done when
- exception classes are semantically aligned with the operation that failed
- error objects carry enough context for debugging

---

## Phase 10: Improve Test Coverage Where It Matters Most

### Goal
Prevent the exact regression class that caused the current problems.

### Files to add or extend
- `tests/types/test_golden.py` **new**
- `tests/types/test_generated_shapes.py` **new**
- `tests/types/test_ir_normalization.py` **new**
- `tests/api/test_event_stream.py`
- `tests/integration/test_event_flow.py`

### High-value golden fixtures to add
Store representative raw JSON payloads for:
- outputs reply with full nested output/mode structure
- focused output reply with nullable payload
- focused window reply with nullable payload
- picked color reply
- windows/workspaces/layers replies
- one event payload with nested structs
- one action payload with list[str]

### Principle
Prefer a small number of realistic fixtures over many tiny synthetic ones.

### Minimum coverage additions
1. **IR normalization tests** for canonical type preservation
2. **Generated shape tests** for key annotations
3. **Reply roundtrip tests** for payload survival
4. **Event stream behavior tests** for close/error/backpressure semantics
5. **verify-generated smoke test** if practical in CI

### Done when
- the original generation bug would now fail multiple tests
- the original event-stream close bug would now fail at least one test deterministically

---

## Phase 11: Final Hygiene and CI Guardrails

### Goal
Make the repo hard to regress accidentally.

### Tasks
1. Ensure `.gitignore` excludes:
   - `__pycache__/`
   - `*.pyc`
   - `.pytest_cache/`
   - Rust `target/`
2. Confirm README and contributor docs state:
   - generated files must not be edited manually
   - regeneration flow
   - pinned upstream version
3. Ensure CI or local verification sequence includes:
   - normalizer
   - generator
   - verify-generated
   - tests
   - lint
   - format check
   - type check

### Recommended verification commands
```bash
uv sync --extra dev
python tools/normalize_ir.py --schema-dir schema/exported --output schema/ir/niri-ipc-ir.json --upstream-pin schema/upstream-pin.toml
python tools/generate_types.py --ir schema/ir/niri-ipc-ir.json --output-dir src/niri_pypc/types/generated
python tools/verify_generated.py --ir schema/ir/niri-ipc-ir.json --generated-dir src/niri_pypc/types/generated
PYTHONPATH=src pytest -q
ruff check .
ruff format --check .
ty check .
```

### Done when
- repo is clean
- docs match reality
- quality gates are unambiguous

---

## File-by-File Change Checklist

Use this as a punch list.

### `tools/normalize_ir.py`
- [ ] reorder schema-shape handling to preserve arrays/maps/options/refs
- [ ] add helper functions for optional detection and array normalization
- [ ] fix variant classification for optional refs and other non-object payloads
- [ ] add unit tests for normalization behavior

### `tools/generate_types.py`
- [ ] verify `ir_type_to_python()` preserves nested structure
- [ ] verify newtype variants always emit `payload: ...`
- [ ] ensure deterministic ordering/imports
- [ ] regenerate outputs instead of patching generated files manually

### `src/niri_pypc/types/codec.py`
- [ ] make encode behavior structural
- [ ] make reply unwrap behavior structural
- [ ] stop using decode-flavored exceptions for encode failures

### `src/niri_pypc/api/event_stream.py`
- [ ] replace bare sentinel approach with explicit queue item types
- [ ] surface transport/decode failures to consumers
- [ ] make close queue-safe under full capacity
- [ ] stop using background socket read timeout as idle stream killer
- [ ] make async iteration end with `StopAsyncIteration`
- [ ] keep shutdown idempotent

### `src/niri_pypc/api/client.py`
- [ ] make `connect()` align with documented async contract
- [ ] integrate lifecycle honestly
- [ ] optionally add explicit compatibility check helper

### `src/niri_pypc/api/bundle.py`
- [ ] stop mutating lifecycle private state directly
- [ ] await async client connect if changed
- [ ] keep member independence semantics intact

### `src/niri_pypc/errors.py`
- [ ] add missing error classes if chosen (`EncodeError`, `CompatibilityError`)
- [ ] preserve context fields consistently
- [ ] keep payload excerpts bounded

### Tests
- [ ] add normalization tests
- [ ] add generated-shape tests
- [ ] add golden reply fixtures/tests
- [ ] add event-stream close/error/backpressure tests

### Repo hygiene
- [ ] remove caches and build outputs
- [ ] update ignore rules

---

## Suggested Commit Sequence

Make small reviewable commits in this order:

1. `chore: remove tracked cache/build artifacts and tighten ignore rules`
2. `test: add regression coverage for generated reply payload fidelity`
3. `test: add event stream shutdown and timeout regression tests`
4. `refactor: preserve arrays options and refs in IR normalization`
5. `refactor: regenerate protocol types from corrected IR`
6. `refactor: make codec reply handling structural`
7. `refactor: redesign event stream terminal/error queue semantics`
8. `refactor: align client and bundle lifecycle behavior with spec`
9. `feat: implement strict version compatibility check` or `refactor: remove dead strict_version_check config`
10. `test: add golden fixtures and generated shape coverage`
11. `docs: update contributor workflow and regeneration guidance`

This sequence makes debugging and review much easier.

---

## Final Acceptance Checklist

Do not call the refactor done until every item below is true.

### Generation pipeline
- [ ] `normalize_ir.py` preserves arrays, refs, maps, and options correctly
- [ ] regenerated types no longer degrade known fields to `Any`
- [ ] known broken reply models now carry real payload types
- [ ] `verify_generated` passes cleanly

### Runtime behavior
- [ ] `NiriEventStream.close()` is idempotent and queue-safe
- [ ] transport failures from reader surface to consumer as transport errors
- [ ] malformed inbound events do not get silently swallowed
- [ ] idle event streams do not self-destruct due to background read timeout misuse
- [ ] `__anext__()` raises `StopAsyncIteration` on closure

### API / lifecycle
- [ ] no class mutates `LifecycleManager._state` directly
- [ ] `NiriClient.connect()` matches the documented contract
- [ ] bundle preserves independence between client and event stream
- [ ] `strict_version_check` is either implemented or removed

### Tests and hygiene
- [ ] high-value golden fixtures exist
- [ ] generator and normalization logic have direct regression coverage
- [ ] repo contains no tracked cache/build junk
- [ ] full local verification sequence is green

---

## Advice to the Intern

When you feel tempted to “just patch the generated file,” stop. That is almost certainly the wrong layer.

When you feel tempted to swallow an exception in the event reader, stop. The library is supposed to be explicit about protocol/runtime failures.

When a test is hard to write, that often means the design needs one more small helper function or one more internal abstraction. Add the helper. Do not hide the behavior.

The right end state is not merely “working.” It is:
- deterministic
- explicit
- layered correctly
- easy to reason about
- hard to accidentally break

That is the standard for this refactor.
