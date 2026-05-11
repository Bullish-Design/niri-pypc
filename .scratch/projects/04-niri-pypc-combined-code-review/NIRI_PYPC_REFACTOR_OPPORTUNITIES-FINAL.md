# NIRI_PYPC_REFACTOR_OPPORTUNITIES-FINAL

## Executive summary

After reviewing the concept, specification, implementation guide, the attached `niri-pypc` codebase, and the three prior refactoring investigations, the final conclusion is:

**`niri-pypc` has the correct broad repository shape, but it is not yet a clean, faithful, or elegant implementation of its own architecture.**

The codebase currently suffers from two foundational defects that dominate all other refactoring opportunities:

1. **The schema → IR → generated-types pipeline is lossy.**
   This breaks the library's main promise: pinned, high-confidence protocol typing.
2. **The event stream runtime/lifecycle model is architecturally muddled.**
   This breaks the library's second main promise: predictable runtime behavior for long-lived IPC streams.

Those two areas should be treated as the center of gravity for the refactor. Most other changes are worthwhile, but secondary.

Because backwards compatibility is explicitly not a constraint, the correct strategy is **not** to preserve current incidental APIs or abstractions. The correct strategy is to converge the repository on the cleanest architecture implied by the concept and spec:

- a **strict and lossless protocol-generation pipeline**
- a **minimal command client**
- a **single-purpose event stream**
- a **bundle that is only a coordinator, not a phantom state machine**
- a **small and precise error taxonomy**
- **tests that target the true failure modes**, not just roundtrip happy paths

---

## Scope and source basis

This final analysis was synthesized from five inputs:

1. **The normative project sources**
   - `NIRI_PYPC_CONCEPT_FINAL.md`
   - `NIRI_PYPC_SPEC.md`
   - `NIRI_PYPC_IMPLEMENTATION_GUIDE.md`
2. **The actual attached library codebase** (`niri-pypc.zip`)
3. **The implementation-grade refactoring guide** (`niri_pypc_refactoring_guide.md`)
4. **The broader roadmap-style refactoring report** (`REFACTORING_OPPORTUNITIES.md`)
5. **The elegance-oriented v2.5 report** (`REFACTORING_OPPORTUNITIES_V2_5.md`)

This document is not a rephrasing of any one prior report. It is a final synthesis based on:

- the intended architecture in the concept/spec/implementation guide
- the real repository contents and behavior
- the strengths and weaknesses of the prior investigations
- an explicit bias toward **best architecture and best codebase**, not compatibility preservation

---

## What this library is supposed to be

At its best, `niri-pypc` is a **pinned protocol/runtime substrate** for the `niri` compositor's IPC.

It is **not** supposed to be:

- a compositor state engine
- a reducer/replay/convergence layer
- a reconnection framework
- a policy-heavy client abstraction
- a convenience wrapper that hides protocol realities

Its job is much narrower and more important:

1. export the pinned upstream Rust protocol schema
2. normalize it into a deterministic intermediate representation
3. generate faithful Pydantic models for requests, replies, events, actions, and domain structs
4. provide a runtime transport and API layer that is explicit, predictable, and testable
5. expose a command client and event stream without taking ownership of higher-level state

That architectural split is clearly established in the concept and spec. The library's value comes from preserving the generated/manual boundary and getting both sides right.

---

## What the codebase currently gets right

Before listing refactoring opportunities, it is worth stating what is already structurally correct.

### 1. The repository shape is broadly right

The codebase already has the intended major directories and boundaries:

- `schema/exported/`
- `schema/ir/`
- `tools/`
- `src/niri_pypc/types/generated/`
- `src/niri_pypc/transport/`
- `src/niri_pypc/runtime/`
- `src/niri_pypc/api/`
- `tests/` split by concern

That means this is **not** a codebase that needs conceptual reinvention. It needs **alignment and cleanup**, not a ground-up redesign.

### 2. The generated/manual split exists

The codebase already distinguishes:

- generated protocol types
- handwritten codec/runtime/API code

That is exactly the right top-level design.

### 3. The project is already pinned to a specific upstream crate

The repository is grounded on `niri-ipc 25.11`, and the schema export machinery exists. That is the correct basis for a deterministic protocol substrate.

### 4. The one-connection-per-request command model is the right initial choice

This is still the cleanest command-side model for a strict IPC substrate.

### 5. The event stream is already separated from the command client

This is conceptually right. The event connection is qualitatively different from the request/response command connection and deserves its own API and lifecycle.

---

## What is actually wrong

## A. The protocol generation pipeline is lossy

This is the single most important problem in the repository.

### Why this matters

The central promise of `niri-pypc` is that it gives Python callers a faithful, pinned, typed representation of the upstream protocol.

If the generation pipeline is lossy, then the library fails at its most important job, even if transport and tests appear mostly healthy.

### What I observed in the codebase

The core issue lives in `tools/normalize_ir.py`.

The current `canonical_type()` function classifies by `schema["type"]` too early and too shallowly. In practice this means:

- array schemas get collapsed before their item shape is preserved
- fixed-length arrays using `prefixItems` are not represented faithfully
- map/object-with-`additionalProperties` schemas degrade or are flattened incorrectly
- optional refs expressed via `anyOf` are often misclassified
- unsupported/ambiguous shapes silently fall back to weak defaults like `string` or `ref:Unknown`

That weak IR then flows into `tools/generate_types.py`, which faithfully emits the wrong Python types.

### Concrete symptoms in the attached codebase

The current generated code contains several high-value protocol degradations:

- `SpawnAction.command` is generated as `list[Any]`
- `Output.modes` is generated as `list[Any]`
- `Output.physical_size` is generated as `list[Any] | None`
- `WindowLayout.tile_size` is generated as `list[Any]`
- `WindowLayout.window_offset_in_tile` is generated as `list[Any]`
- `WindowLayout.window_size` is generated as `list[Any]`
- `Response.FocusedOutput` is generated as an empty `pass` class
- `Response.FocusedWindow` is generated as an empty `pass` class
- `Response.Outputs` is generated as an empty `pass` class
- `Response.PickedColor` is generated as an empty `pass` class
- `Response.PickedWindow` is generated as an empty `pass` class
- `Response.Layers`, `Response.Windows`, and `Response.Workspaces` preserve "array-ness" but still degrade to `list[Any]`

These are not cosmetic issues. They materially damage the usability and trustworthiness of the library.

### Root cause analysis

The defects are traceable to three coupled design flaws.

#### 1. Shape classification order is wrong

The current normalizer checks `type` too early.

That causes schemas like:

- `{ "type": "array", "items": { "$ref": ... } }`
- `{ "type": ["array", "null"], "prefixItems": [...] }`
- `{ "type": "object", "additionalProperties": ... }`
- `{ "anyOf": [{ "$ref": ... }, { "type": "null" }] }`

not to survive with enough structure.

#### 2. Fallback behavior is too permissive and too lossy

When the normalizer is unsure, it often chooses a weak default rather than failing or preserving more structure.

That is an anti-pattern for a pinned protocol generator. This layer should prefer:

- precise preservation
- explicit unsupported-shape failure
- deterministic extension of the IR

It should not silently collapse rich schemas into generic placeholders.

#### 3. Variant classification is too shallow

`classify_variants()` incorrectly treats several payload forms as empty structs when they are actually newtypes.

The clearest examples are nullable refs such as:

- `FocusedOutput`
- `FocusedWindow`
- `PickedColor`
- `PickedWindow`

These should be generated as payload-carrying response wrappers, not empty models.

### Additional important correction: `Outputs` is a map, not a list

One of the prior reports used a list-shaped fixture for `Outputs`. The exported schema shows that `Outputs` is actually:

```json
{
  "type": "object",
  "additionalProperties": { "$ref": "#/$defs/Output" }
}
```

So the correct generated type is not `list[Output]`; it is conceptually:

```python
dict[str, Output]
```

This matters because it demonstrates why the final analysis must be grounded in the real schema, not only in prior reports.

### Why this is architecturally unacceptable

If the generation pipeline emits `Any` in precisely the places where the upstream schema is rich and meaningful, the library stops being a typed protocol substrate and starts becoming a partially typed convenience wrapper.

That is the opposite of the concept.

### Final recommendation for this area

This should be the **first refactor** and treated as a foundational architectural repair.

#### Required refactor direction

1. Rewrite `canonical_type()` to be **shape-first**, not primitive-first.
2. Add dedicated helpers for:
   - optional detection and stripping
   - array normalization
   - fixed-length `prefixItems` normalization
   - map normalization
   - primitive fallback
3. Preserve these forms explicitly:
   - `ref:Type`
   - `option<T>`
   - `array<T>`
   - `map<string, T>`
   - intentional fixed-length array shapes where schema requires them
4. Fix variant classification so payloads are classified structurally:
   - only real object-with-fields payloads become `struct`
   - scalar/ref/array/map/option payloads become `newtype`
5. Make the normalizer fail loudly on truly unsupported shapes.
6. Regenerate all protocol files from the corrected IR.

### My recommendation on fixed-length `prefixItems` arrays

The implementation-grade guide suggests preserving homogeneous fixed-length arrays as ordinary arrays unless forced to do more.

That is a reasonable default and should not be treated as a quality compromise by itself.

Because compatibility is not a constraint here, I recommend preserving element-level intent clearly, but without requiring tuple syntax in the IR as a hard architectural rule.

Examples that should be represented more faithfully than `list[Any]` or even generic `list[float]`:

- 2D positions
- 2D sizes
- RGB triples
- integer index pairs

The clean design is:

- IR explicitly distinguishes generic arrays from fixed-length `prefixItems` arrays
- generator emits a deliberate representation that preserves intent (typed list, fixed-length alias, or tuple where justified)
- tests enforce the representation on real protocol fields

The important constraint is preserving structure and semantics, not enforcing one syntax choice everywhere.

---

## B. The event stream runtime model is architecturally wrong

This is the second major refactoring target.

### Why this matters

The event stream is the most lifecycle-sensitive, concurrency-sensitive part of the runtime.

A command client can recover from mediocre design because each request gets a fresh connection and a small scope. A persistent event stream cannot.

If its close path, error propagation, backpressure behavior, and timeout behavior are not explicit and robust, the entire API becomes untrustworthy.

### What I observed in the codebase

The current implementation of `NiriEventStream` mixes several concerns together:

- event delivery
- internal terminal signaling
- lifecycle transitions
- backpressure responses
- reader failure handling
- consumer timeout behavior

The queue stores `BaseModel | _StreamClosed`, where `_StreamClosed` is an exception-like sentinel. This sentinel is being used to represent multiple different realities:

- deliberate user close
- remote disconnect
- background reader termination
- possibly backpressure shutdown

That design is too ambiguous.

### Concrete problems in the current implementation

#### 1. `close()` can raise `asyncio.QueueFull`

Both `close()` and `_close_from_reader()` call `put_nowait(_StreamClosed())` into a bounded queue without safely handling full-queue conditions.

This makes `close()` not reliably idempotent and not reliably safe.

For a resource close path, that is unacceptable.

#### 2. Malformed events are silently swallowed

The reader currently does:

```python
except Exception:
    # Malformed event — skip it
    continue
```

and also wraps the loop in an even broader `except Exception: pass`.

This destroys observability and correctness.

For a pinned protocol client, malformed inbound events are not harmless noise. They are meaningful protocol or decode failures.

#### 3. Transport failures collapse into generic closure

The reader catches `TransportError`, breaks, and eventually closes the stream via the same sentinel path used for ordinary close.

That means consumers cannot reliably distinguish:

- graceful closure
- transport breakage
- decode failure
- backpressure failure

That is the wrong API surface.

#### 4. `event_read_timeout` is used in the background reader

The background task calls `conn.read_frame(..., timeout=config.event_read_timeout)`.

This means an idle stream can self-destruct simply because no event arrived quickly enough.

That is a semantic mismatch.

A background event stream should usually be allowed to stay idle indefinitely. Timeouts belong at the consumer wait boundary, not the socket-idle boundary, unless the API explicitly promises a heartbeat-based timeout policy.

#### 5. `__anext__()` does not implement correct async-iteration semantics

`__anext__()` simply forwards `await self.next()` and does not convert stream closure into `StopAsyncIteration`.

That means the iteration contract is not being honored explicitly.

#### 6. Lifecycle signaling is inconsistent and overloaded

The stream uses `LifecycleManager`, but the actual runtime semantics are split between:

- lifecycle state
- connection presence
- reader task state
- queue sentinel state

This increases the number of ways the stream can become "effectively closed" without one authoritative channel.

### Why this design is not elegant

The elegant design for a stream is not:

- "push events into a queue and occasionally insert a sentinel"

The elegant design is:

- maintain one explicit internal channel with distinct item types
- separate ordinary events from terminal conditions and real failures
- keep lifecycle transitions aligned with actual resource ownership
- keep socket idle policy separate from consumer wait policy

### Final recommendation for this area

Refactor `NiriEventStream` around explicit queue item types.

#### Recommended internal model

Use something like:

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

Queue type:

```python
asyncio.Queue[_EventItem | _ErrorItem | _ClosedItem]
```

#### Required behavioral changes

1. Successful reader decode → enqueue `_EventItem`
2. Decode failure → enqueue `_ErrorItem`, then terminate stream
3. Transport failure → enqueue `_ErrorItem`, then terminate stream
4. User close → enqueue `_ClosedItem`
5. `next()` dispatches on actual internal item type
6. `__anext__()` converts closed-stream terminal state to `StopAsyncIteration`
7. Queue insertion for terminal items should be non-blocking and full-queue-safe
8. `close()` should be idempotent and should not fail because the queue is full

### Timeout policy recommendation

The cleanest interpretation is:

- `next(timeout=...)` controls consumer wait time
- default `next()` timeout may use `config.event_read_timeout`
- the background reader should not use `event_read_timeout` to police idle sockets

If retaining the config knob, reinterpret it as a **default consumer timeout**, not a background socket read timeout.

### Decode-failure policy recommendation

Do **not** log and continue.

Do **not** skip malformed events.

For a pinned substrate library, malformed events are a fatal protocol/decode failure. The stream should surface that failure and terminate.

### Backpressure policy recommendation

The conceptual backpressure policy is sound:

- `DROP_OLDEST`
- `FAIL_FAST`

But the implementation should be made explicit and observable.

In particular:

- `DROP_OLDEST` should intentionally replace the oldest queued event
- `FAIL_FAST` should surface a real error item, not collapse into silent close
- close/error markers should displace stale events if the queue is full

That last point is important: **terminal stream state should outrank stale queued events**.

---

## C. `NiriClient` is over-engineered for the resource it actually is

### What I observed

`NiriClient` currently owns a `LifecycleManager`, but it does not own a persistent connection.

Each request opens a new socket, sends a request, reads one reply, and closes the socket.

In practice, that means the client is not a connection state machine. It is a lightweight request facade with a closed flag.

### Why the current design is inelegant

A lifecycle manager is justified when a class owns meaningful phases such as:

- init
- connecting
- ready
- closing
- closed

`NiriEventStream` has those semantics.

`NiriClient` mostly does not.

Using `LifecycleManager` here adds:

- mental overhead
- indirection
- a state abstraction that does not correspond to a real socket lifetime
- a mismatch between conceptually simple behavior and implementation machinery

### The `connect()` contract is also awkward

The concept/spec describe `connect()` as async, while the implementation makes it synchronous.

That mismatch is real, but because compatibility is irrelevant here, I would not preserve either side out of loyalty. I would choose the cleanest final API.

### Final recommendation for `NiriClient`

I recommend simplifying aggressively.

#### Best final design

- remove `LifecycleManager` from `NiriClient`
- store `self._closed: bool`
- keep one-connection-per-request
- keep `close()` idempotent and simple
- keep async context manager support
- do not invent persistent-client state that does not exist

#### On the constructor/factory shape

There are two clean options:

##### Option A: plain constructor + async context manager

```python
client = NiriClient(config)
async with client:
    ...
```

##### Option B: sync `connect()` factory returning a ready-to-use lightweight client

```python
client = NiriClient.connect(config)
async with client:
    ...
```

Either is cleaner than carrying a fake lifecycle. The important point is that `connect()` should not pretend to establish a durable connection when it does not.

### Additional client-side cleanup

- use `UnixConnection` as an async context manager
- avoid inline imports in hot paths unless necessary for cycle-breaking
- consider explicit request encode/decode helper boundaries
- keep `request()` narrowly focused on one request/response flow

### Non-recommendation: do not add connection pooling

One prior report mentions a possible connection pool or persistent command connection.

I do **not** recommend it for the final design here.

Reasons:

- it complicates correctness significantly
- it adds lock orchestration and retry semantics
- it weakens error isolation between requests
- it moves away from the simple upstream-aligned one-request-per-connection model
- there is no evidence that it is needed

For this library's purpose, command simplicity is more valuable than speculative performance engineering.

---

## D. `NiriConnectionBundle` should not have its own lifecycle at all

### What I observed

The current bundle creates a `LifecycleManager` and then directly mutates:

```python
self._lifecycle._state = LifecycleState.READY
```

This is one of the clearest design smells in the repository.

### Why this is bad

- it bypasses the abstraction the class supposedly depends on
- it proves the abstraction is a poor fit for the bundle
- it invents bundle-level state that has no independent meaning
- it makes the bundle more complicated than its actual role requires

### The bundle's real role

`NiriConnectionBundle` is not a stateful resource in its own right.

It is a convenience wrapper over two independent resources:

- a command client
- an event stream

It should coordinate their construction and coordinated teardown. That is all.

### Final recommendation

Delete bundle lifecycle entirely.

#### Best final bundle shape

- bundle owns `client`
- bundle owns `events`
- bundle exposes `.client` and `.events`
- `open()` constructs both
- `close()` closes both, preserving best-effort independent shutdown
- bundle does not maintain a separate lifecycle manager

This is cleaner than:

- the current private-state mutation hack
- adding `skip_to_ready()` to `LifecycleManager`
- preserving a phantom state machine just to avoid admitting the bundle is a simple coordinator

### Error-isolation semantics

The concept is clear that the bundle should preserve independence:

- event stream failure should not invalidate the client
- client request failure should not force-close the event stream

That independence is easier to preserve when the bundle is **thin**.

A thin coordinator is the cleanest design.

---

## E. Codec and reply handling should become fully structural

### What I observed

The codec layer is close to reasonable, but it still contains two avoidable architectural flaws.

#### 1. `encode_externally_tagged()` raises `DecodeError`

If an outbound variant class is unknown, the current code raises a decode-oriented exception.

That is semantically wrong.

#### 2. `unwrap_reply()` dispatches using class-name prefixes

The current implementation checks whether the reply variant class name starts with `Ok` or `Err`.

That is fragile and unnecessary.

### Why this matters

This library is small enough that the codec layer should be crisp and obvious. Error meaning should match the operation that failed, and structural protocol logic should not depend on naming conventions.

### Final recommendation

#### Add `EncodeError`

Encoding failures should raise an encoding-oriented exception.

That can be either:

- a dedicated `EncodeError`
- or `ProtocolError` if you prefer a smaller public taxonomy

My preference is `EncodeError`, because this is a protocol codec layer and the distinction is useful and clear.

#### Make externally tagged encode fully structural

Encode behavior should be defined by field structure only:

- no fields → unit variant → return wire-name string
- exactly one field named `payload` → newtype variant → return `{wire_name: payload}`
- otherwise → struct variant → return `{wire_name: dumped_model_dict}`

The current code is almost there; it just needs semantic cleanup.

#### Make `unwrap_reply()` structural

Do not dispatch on class-name strings.

Use actual reply types or actual variant mappings.

Best approach:

- inspect `reply.variant`
- if it is `OkReply`, return its payload
- if it is `ErrReply`, raise `RemoteError`
- otherwise raise `DecodeError`

That is obvious, type-checkable, and robust.

#### Avoid broad `getattr()` heuristics when direct structure is known

Where the generated contract is clear, prefer direct field access over dynamic reflection.

### One subtlety to decide explicitly

At present, `client.request()` returns the unwrapped `Ok` payload, which is still the response variant model rather than the raw inner scalar/list/dict value.

That is a defensible design. It preserves typed response variants rather than collapsing everything to raw payload primitives.

I recommend keeping that design, but documenting it clearly and consistently.

---

## F. Error taxonomy should be tightened, not expanded indiscriminately

### What I observed

The current error hierarchy is mostly correct, but incomplete and somewhat under-contextualized.

Good aspects:

- there is a proper shared base class
- timeout is dual-inherited from `TimeoutError`
- remote, decode, lifecycle, config, transport, and internal errors are separated

Problems:

- encode failures do not have the right error class
- `cause` is not stored explicitly
- payload truncation is not centralized
- some raised errors do not carry as much context as they could

### Final recommendation

Keep the taxonomy small and crisp.

#### Recommended error set

- `NiriError`
- `TransportError`
- `NiriTimeoutError`
- `DecodeError`
- `EncodeError`
- `ProtocolError`
- `RemoteError`
- `LifecycleError`
- `ConfigError`
- `InternalError`
- optional: `CompatibilityError`

### Error context recommendations

All operational errors should carry as much of the following as makes sense:

- `operation`
- `socket_path`
- `retryable`
- `state`
- `remote_message`
- `raw_payload` (bounded)
- `cause`

### Truncation recommendation

`DecodeError.raw_payload` truncation should be centralized in one helper rather than hand-coded in multiple places.

### Chaining recommendation

The codebase should consistently use `raise ... from exc` and also preserve `cause` on the error object itself.

That gives both Python-native traceback chaining and explicit machine-readable access.

---

## G. The fate of `strict_version_check` must be decided explicitly

### What I observed

`NiriConfig` defines:

```python
strict_version_check: bool = True
```

But there is no implementation behind it.

### Why this matters

Dead configuration is one of the worst forms of architectural dishonesty.

It tells readers and users that the system has a policy it does not actually enforce.

### Final recommendation

I recommend **removing the config field** for now.

### Why remove rather than implement immediately

- it is currently dead code
- the library has more urgent correctness problems
- version mismatch is a real concern, but it does not need to be hidden behind automatic client behavior
- a clear explicit method is better than a silent config flag

### Best later design

If version compatibility checking is added later, it should look more like:

```python
await client.check_version_compatibility(strict=True)
```

rather than an implicit hidden check wired into construction or first request.

That is more explicit and easier to reason about.

### Acceptable alternative

If you strongly want version mismatch policy in the first-class API now, then implement it properly and add a dedicated `CompatibilityError`.

Leaving the dead knob in place is not desirable for the target architecture.

---

## H. The tests are not aimed at the right failure modes

### What I observed

The current test suite is decent in breadth and passes under `PYTHONPATH=src`, but it misses the exact areas where the implementation is weakest.

That is why the suite can be green while the library still has serious architectural defects.

### What is currently under-tested or untested

#### 1. IR normalization fidelity

There are no focused tests that prove arrays, maps, optional refs, and fixed-length `prefixItems` shapes survive normalization correctly.

#### 2. Generated annotation fidelity

There are no targeted tests that assert high-value generated field annotations for the known-problem shapes.

#### 3. Reply payload survival

The suite does not lock down the correctness of the broken response variants strongly enough.

#### 4. Event stream shutdown/error/backpressure behavior

The suite does not adequately test:

- queue-full close behavior
- transport-vs-close differentiation
- decode error surfacing
- timeout semantics under idle streams
- async iteration contract on close

### Final recommendation

The next wave of tests should be designed as regression tests for architecture-defining behavior, not just API smoke tests.

#### Must-add tests

##### Type/generation pipeline

- `tests/types/test_ir_normalization.py`
- `tests/types/test_generated_shapes.py`
- `tests/types/test_golden.py`

##### High-value protocol assertions

- `SpawnAction.command` is `list[str]`
- `Output.modes` is `list[Mode]`
- `OutputsResponse` preserves `dict[str, Output]`
- `FocusedOutputResponse.payload` is `Output | None`
- `FocusedWindowResponse.payload` is `Window | None`
- `PickedColorResponse.payload` is `PickedColor | None`
- `PickedWindowResponse.payload` is `Window | None`
- `LayersResponse.payload` is `list[LayerSurface]`
- `WindowsResponse.payload` is `list[Window]`
- `WorkspacesResponse.payload` is `list[Workspace]`
- `WindowLayout` coordinate/size fields preserve fixed-length numeric structure
- `PickedColor.rgb` preserves fixed-length triple structure

##### Event stream behavior

- `test_close_with_full_queue_does_not_raise`
- `test_transport_error_surfaces_from_next`
- `test_decode_error_surfaces_from_next`
- `test_event_read_timeout_only_affects_next_wait`
- `test_async_iteration_stops_cleanly`
- `test_fail_fast_backpressure_surfaces_error`
- `test_drop_oldest_replaces_oldest_event`

### Testing principle recommendation

Use a **small number of realistic golden fixtures** rather than many tiny synthetic fragments. This library is protocol-centric; realism matters.

---

## I. Generator determinism and repo hygiene still need cleanup

### What I observed

The attached repo includes committed build output under:

- `tools/schema_exporter/target/`

That should not be in version control.

Also, `verify_generated` currently fails, but the observed diff is mostly formatting/layout drift rather than deep semantic drift.

That is still a problem because deterministic generation is one of the library's core invariants.

### Why this matters

A protocol-generation project lives or dies on reproducibility discipline.

If generated artifacts are noisy, non-deterministic, or mixed with build junk, then:

- reviews become harder
- drift becomes harder to interpret
- CI becomes less trustworthy
- the generated/manual boundary gets fuzzier

### Final recommendation

#### Repo hygiene

- remove `tools/schema_exporter/target/` from the repository
- ensure `.gitignore` covers build and cache outputs
- keep generated directories clean and authoritative

#### Generator determinism

- stabilize output formatting and blank-line behavior
- ensure import groups are deterministic
- ensure unions/variants/fields/types are ordered deterministically
- make `verify_generated` a hard gate that is expected to stay green

### Important prioritization note

This is not more important than fixing IR fidelity.

Do **not** waste time polishing output formatting before fixing the semantic loss in the pipeline. Deterministic wrong output is still wrong.

---

## J. Small but worthwhile cleanup opportunities

These are real improvements, but should be deliberately deprioritized.

### 1. Make `UnixConnection` an async context manager

This is a clean improvement.

It simplifies client-side request code and reduces the need for explicit `try/finally` blocks.

Recommended.

### 2. Simplify `UnixConnection.close()`

The current implementation uses defensive `hasattr()` checks around writer close methods that are not really needed for the intended runtime object.

This is a low-risk cleanup.

### 3. Move unnecessary inline imports to module scope

Good hygiene unless they are truly cycle-breaking.

### 4. Add `__all__` where it improves package boundary clarity

Useful but low priority.

### 5. Add logging for dropped events/backpressure

Useful, but secondary to fixing semantics. Logging should not be used as a substitute for correct error propagation.

### 6. Improve docs and contributor workflow guidance

Valuable after the architectural changes stabilize.

---

## Cross-report synthesis: what the prior investigations got right and wrong

## The implementation-grade refactoring guide

### Strengths

This is the strongest prior investigation.

It correctly identifies:

- the generation pipeline as the first priority
- the event stream as the second priority
- the need for regression tests before behavioral changes
- the need to keep generated/manual boundaries strict
- the need to fix `unwrap_reply()` structurally
- the need to make `verify_generated` green
- the need to either implement or remove `strict_version_check`

### Limitations

Its one conservative tendency is that it slightly favors intern-safe implementation choices over the cleanest possible final architecture.

Examples:

- keeping fixed-length `prefixItems` arrays as generic arrays unless forced otherwise
- preserving more lifecycle structure than may actually be needed for the client/bundle

Those are understandable compromises, but given the explicit no-compatibility constraint, the final architecture can be cleaner than the guide's minimum viable fix.

## The broader roadmap-style refactoring report

### Strengths

It is directionally right about:

- simplifying `NiriClient`
- deleting the bundle state hack
- adding `EncodeError`
- fixing `unwrap_reply()`
- deferring connection pooling
- making `UnixConnection` an async context manager

### Limitations

It underweights the severity of the generation-pipeline problem relative to runtime ergonomics.

Several of its best recommendations are good, but they should come **after** the IR/generation repair, not before it.

## The v2.5 elegance-oriented report

### Strengths

It adds useful polish-minded recommendations around:

- observability
- `cause` tracking in errors
- backpressure logging
- low-level code cleanup

### Limitations

It is too forgiving in one important place: the suggestion to log malformed events and continue.

That is not the preferred policy for a pinned protocol substrate. In this library, malformed inbound events should terminate the stream with a real decode/protocol failure.

It also suggests `skip_to_ready()` for the bundle lifecycle. That is cleaner than direct private-state mutation, but still preserves an abstraction I believe should be removed altogether.

---

## Final ranked refactoring opportunities

## P0 — Repair the schema → IR → generated type pipeline

### Why it is P0

Because protocol fidelity is the library's primary reason to exist.

### Files

- `tools/normalize_ir.py`
- `tools/generate_types.py`
- `schema/ir/niri-ipc-ir.json`
- `src/niri_pypc/types/generated/*`
- new pipeline tests

### End-state goal

Generated protocol types should faithfully and deterministically encode the actual pinned upstream protocol shapes, with no unnecessary `Any` and no empty fake wrappers where payload-carrying newtypes are required.

### Required changes

- rewrite `canonical_type()` shape-first
- preserve arrays, maps, options, refs, and fixed-length `prefixItems` intent
- fix variant classification
- regenerate all types
- add focused generation tests
- make `verify_generated` green

### Acceptance criteria

- `SpawnAction.command` is `list[str]`
- `Output.modes` is `list[Mode]`
- `OutputsResponse.payload` is `dict[str, Output]`
- `FocusedOutputResponse.payload` is `Output | None`
- `FocusedWindowResponse.payload` is `Window | None`
- `PickedColorResponse.payload` is `PickedColor | None`
- `PickedWindowResponse.payload` is `Window | None`
- `LayersResponse.payload` is `list[LayerSurface]`
- `WindowsResponse.payload` is `list[Window]`
- `WorkspacesResponse.payload` is `list[Workspace]`
- fixed-length `prefixItems` structures are represented intentionally and consistently
- `verify_generated` exits 0

## P0 — Refactor `NiriEventStream` Semantics

### Why it is P0

Because it is the core long-lived runtime abstraction and currently has ambiguous semantics around closure and failure.

### Files

- `src/niri_pypc/api/event_stream.py`
- `src/niri_pypc/errors.py`
- event-stream tests

### End-state goal

The stream should have one explicit event/error/closed channel, clean close semantics, correct async iteration behavior, and unambiguous surfacing of transport and decode failures.

### Required changes

- replace sentinel queue with explicit internal queue item types
- surface decode failures as failures, not skipped warnings
- surface transport failures distinctly
- make close queue-safe under full capacity
- separate socket idle policy from consumer wait policy
- make `__anext__()` translate ordinary closure into `StopAsyncIteration`

### Acceptance criteria

- close never raises due to full queue
- transport failures surface as transport failures
- malformed events surface as decode/protocol failures
- idle streams do not self-destruct due to background read timeout misuse
- `async for` ends cleanly on deliberate close

## P1 — Simplify `NiriClient`

### Why it is P1

Because the current design is not broken in the same way the pipeline/stream are, but it is over-architected.

### Files

- `src/niri_pypc/api/client.py`
- maybe `src/niri_pypc/transport/connection.py`

### End-state goal

A small, obvious command client with no fake lifecycle state.

### Required changes

- remove `LifecycleManager`
- use `_closed: bool`
- keep one-connection-per-request
- optionally use `UnixConnection` as async context manager
- choose a final constructor/factory style and document it clearly

### Acceptance criteria

- no lifecycle manager in client
- client rejects post-close requests cleanly
- request flow remains simple and explicit

## P1 — Delete bundle lifecycle and keep bundle thin

### Why it is P1

Because the current implementation has an obvious architectural smell and the simplest fix is also the best design.

### Files

- `src/niri_pypc/api/bundle.py`

### End-state goal

A pure coordinator object, not a pseudo-resource with its own state machine.

### Required changes

- remove bundle lifecycle manager
- remove direct `_state` mutation
- coordinate open/close only
- preserve member independence semantics

### Acceptance criteria

- bundle has no lifecycle manager
- bundle close remains idempotent
- bundle preserves client/event independence

## P1 — Make codec and error taxonomy precise

### Why it is P1

Because these are conceptually important and easy to make elegant once the foundations are fixed.

### Files

- `src/niri_pypc/types/codec.py`
- `src/niri_pypc/errors.py`
- `src/niri_pypc/transport/framing.py`

### End-state goal

Structural codec logic and semantically correct failure types.

### Required changes

- add `EncodeError`
- make reply unwrap structural
- centralize truncation helper
- add `cause` tracking
- wrap frame-encoding failures properly

### Acceptance criteria

- no decode errors for encode failures
- no class-name-prefix heuristics in reply unwrap
- better contextual information on raised errors

## P1 — Remove or implement version compatibility policy

### Why it is P1

Because dead configuration should not remain in a polished architecture.

### Files

- `src/niri_pypc/config.py`
- maybe `src/niri_pypc/api/client.py`
- docs/tests

### End-state goal

Either:

- no dead version-check knob, or
- a real, explicit compatibility check with tests

### Recommended choice

Remove it for now.

## P1 — Add real regression tests for the architecture-defining behaviors

### Why it is P1

Because the codebase currently allows green tests despite real correctness and architecture defects.

### Files

- new and expanded test modules in `tests/types/` and `tests/api/`

### End-state goal

The original defects should be difficult to reintroduce silently.

## P2 — Clean generator determinism and repo hygiene

### Why it is P2

Because it matters, but should follow semantic correctness work.

### Files

- `.gitignore`
- `tools/verify_generated.py`
- generator formatting templates
- repo cleanup

### End-state goal

A clean repository with deterministic generated artifacts and no tracked build output.

## P3 — General polish and ergonomics

### Items

- async context manager on `UnixConnection`
- module-level imports where appropriate
- `__all__` cleanup
- improved docstrings and docs
- logging polish

---

## Refactorings I explicitly do **not** recommend

Because backwards compatibility is irrelevant, it is important to be equally explicit about changes that still should **not** be made.

### 1. Do not patch generated files manually

Even for quick wins. It destroys the architecture.

### 2. Do not preserve lifecycle abstractions that do not correspond to real resources

In particular:

- no lifecycle manager in the client
- no lifecycle manager in the bundle

### 3. Do not swallow malformed inbound events

Not even with logging.

### 4. Do not keep dead config knobs

### 5. Do not add connection pooling yet

It is unnecessary complexity.

### 6. Do not over-optimize micro-performance

This library's current problems are semantic and architectural, not performance-bound.

### 7. Do not treat formatting-only generator determinism work as a substitute for semantic fixes

---

## Recommended target architecture

The target final architecture should look like this.

## Layer 1: Protocol authority

Owns:

- exported JSON schemas
- normalized IR
- deterministic generator
- generated Pydantic models

Rules:

- no manual edits in generated subtree
- unsupported shapes fail loudly
- deterministic ordering and output
- protocol fidelity outranks implementation convenience

## Layer 2: Codec

Owns:

- externally tagged enum encode/decode
- structural reply unwrapping
- inbound unknown sentinel handling

Rules:

- structural, not name-based
- semantically correct errors
- no broad reflective heuristics when type structure is known

## Layer 3: Runtime transport

Owns:

- Unix socket connection
- frame encoding/decoding
- timeouts
- socket-level errors

Rules:

- no policy drift upward into transport
- no protocol-shape logic in transport
- close is always idempotent

## Layer 4: Public APIs

### `NiriClient`

- lightweight request facade
- no lifecycle manager
- one request per connection
- explicit and minimal

### `NiriEventStream`

- persistent stream resource
- explicit queue item model
- clear distinction between events, closure, and failure
- correct async iteration semantics

### `NiriConnectionBundle`

- coordinator only
- no independent lifecycle
- preserves independence of members

This architecture is the cleanest synthesis of the concept and the attached codebase.

---

## Recommended execution order

This is the order I recommend for the actual refactor.

### Phase 1 — Add regression tests for the known broken behaviors

Do this before any behavior change.

Focus first on:

- reply payload fidelity
- generated type shapes
- queue-full close behavior
- transport/decode error propagation from the stream
- timeout semantics

### Phase 2 — Repair the normalizer

- fix `canonical_type()`
- fix variant classification
- add tuple/map/option preservation
- add normalizer tests

### Phase 3 — Regenerate types and fix the generator only where necessary

- regenerate everything
- inspect diffs
- fix remaining generator issues only when the IR is already correct

### Phase 4 — Make generated verification deterministic and green

- fix formatting drift
- fix ordering drift
- clean repo hygiene

### Phase 5 — Refactor codec and error taxonomy

- add `EncodeError`
- make reply unwrapping structural
- improve error context and truncation handling

### Phase 6 — Refactor `NiriEventStream` semantics

- explicit queue item types
- queue-safe close/error insertion
- proper timeout semantics
- correct async iteration behavior

### Phase 7 — Simplify `NiriClient`

- remove lifecycle manager
- keep client minimal

### Phase 8 — Thin out `NiriConnectionBundle`

- remove bundle lifecycle entirely
- preserve coordination only

### Phase 9 — Remove or explicitly implement version compatibility policy

Recommended: remove for now.

### Phase 10 — Final cleanup and documentation

- contributor workflow
- generated/manual boundary docs
- final acceptance sequence

---

## File-by-file final direction

## `tools/normalize_ir.py`

### Keep

- the existence of a standalone normalization phase
- IR hashing and upstream metadata capture

### Change

- canonical type classification order
- array/map/tuple/option preservation
- fallback behavior
- variant classification

### Delete

- silent lossy fallback behavior that masks unsupported shapes

## `tools/generate_types.py`

### Keep

- deterministic generation model
- separate generated modules
- root externally-tagged enum models

### Change

- type emission for fixed-length tuple structures if IR is extended
- import stability/formatting determinism
- minimal import sets where convenient

### Do not do

- hand-edit outputs instead of fixing generator/IR

## `src/niri_pypc/types/codec.py`

### Keep

- dedicated codec ownership of externally-tagged encode/decode

### Change

- add `EncodeError`
- make reply unwrap structural
- tighten encode/decode semantics

## `src/niri_pypc/api/event_stream.py`

### Keep

- separate event-stream abstraction
- bounded queue concept
- explicit backpressure modes

### Change

- queue item architecture
- reader failure policy
- close semantics
- timeout semantics
- async iteration contract

### Delete

- sentinel-overloaded ambiguity
- broad exception swallowing

## `src/niri_pypc/api/client.py`

### Keep

- one-connection-per-request model
- request/response flow
- async context manager support

### Change

- lifecycle strategy
- possibly connect/factory shape

### Delete

- lifecycle manager

## `src/niri_pypc/api/bundle.py`

### Keep

- dual-resource convenience wrapper
- coordinated open/close
- member independence

### Change

- simplify implementation to thin coordinator

### Delete

- bundle lifecycle manager
- direct `_state` mutation

## `src/niri_pypc/errors.py`

### Keep

- broad taxonomy categories

### Change

- add `EncodeError`
- optional `CompatibilityError`
- explicit `cause`
- consistency of contextual fields
- bounded truncation helper

## `src/niri_pypc/transport/connection.py`

### Keep

- minimal Unix socket wrapper
- timeout/error mapping

### Change

- optional async context manager
- simplify `close()`

## `src/niri_pypc/transport/framing.py`

### Keep

- compact JSON newline framing

### Change

- wrap encode-side serialization errors properly

---

## Final acceptance criteria

The refactor should not be considered complete until all of the following are true.

## Protocol generation

- arrays, maps, options, refs, and fixed-length `prefixItems` structures are preserved faithfully
- no high-value protocol fields degrade to `Any` without necessity
- known broken response wrappers now carry real payload types
- generated output is deterministic and `verify_generated` is green

## Runtime behavior

- stream close is idempotent and queue-safe
- stream transport failures surface as transport failures
- malformed inbound events surface as decode/protocol failures
- idle streams remain open unless explicitly closed or disconnected
- async iteration ends cleanly on ordinary stream closure

## API architecture

- `NiriClient` no longer carries a fake lifecycle machine
- `NiriConnectionBundle` no longer carries its own lifecycle machine
- bundle preserves independence semantics between client and events
- version compatibility policy is either removed or implemented explicitly

## Tests and hygiene

- the current pipeline bugs are covered by direct tests
- the current stream bugs are covered by direct tests
- no committed build/cache junk remains in the repository
- docs clearly state generated/manual boundaries and regeneration workflow

---

## Final verdict

The codebase does **not** need a wholesale conceptual redesign. It already has the right major boundaries.

What it needs is a **strict alignment refactor**:

1. make the generation pipeline truly faithful
2. make the event stream explicit and failure-transparent
3. remove lifecycle abstractions that do not correspond to real resources
4. tighten codec/error semantics
5. add regression tests in the places that actually define the library's value

If those changes are made, `niri-pypc` becomes exactly what the concept intended:

- a narrow
- pinned
- deterministic
- strongly typed
- runtime-correct
- architecturally honest substrate for Niri IPC in Python

That is the cleanest, most elegant final shape for the project.
