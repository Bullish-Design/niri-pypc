# NIRI_PYPC_CODE_REVIEW_FINAL

Date: 2026-05-11

Scope: Final authoritative review of the attached `niri-pypc` repository, synthesized from:
- the full codebase (`niri-pypc`)
- the concept document (`NIRI_PYPC_CONCEPT_FINAL.md`)
- the implementation specification (`NIRI_PYPC_SPEC.md`)
- the implementation guide (`NIRI_PYPC_IMPLEMENTATION_GUIDE.md`)
- the prior review reports (`niri_pypc_code_review.md`, `INITIAL_CODE_REVIEW.md`, `INITIAL_CODE_REVIEW_v2.5.md`)

This document is intended to be the final review reference for remediation planning. It focuses on issues that should be fixed, refactored, or improved before the library can credibly claim protocol-correctness and production readiness as a pinned `niri-ipc 25.11` client.

---

## 1. Executive summary

`niri-pypc` has a strong intended architecture and a lot of good implementation work. The repository cleanly separates generated protocol types from hand-written transport/runtime logic, uses a sensible one-connection-per-request command model, exposes a usable event stream abstraction, and already has a meaningful automated test suite.

However, the library is **not yet protocol-correct** against its own pinned contract.

The dominant problem is the **schema -> IR -> generation pipeline**. The current normalization and generation flow loses protocol information for arrays, maps, tuple-like arrays, and nullable reference payloads. That information loss propagates into incorrect generated models, degraded typing, and at least some **broken reply round-trips that discard payload data**.

That issue is more important than the smaller runtime, lint, style, or type-check concerns. Until the generation pipeline is corrected and the generated artifacts are regenerated and re-verified, the library should not be described as fully spec-compliant.

### Final verdict

The project is promising and structurally sound, but it currently has:

1. a **critical protocol-fidelity defect** in the generator pipeline,
2. several **high-priority event-stream contract mismatches**, and
3. a set of **medium-priority API, lifecycle, tooling, and repository hygiene issues**.

The codebase does **not** require a redesign. It requires a correctness-first remediation pass.

---

## 2. Review basis and direct validation performed

This final review is based on both static inspection and direct execution against the attached repository.

### Documents consulted

- `NIRI_PYPC_CONCEPT_FINAL.md`
- `NIRI_PYPC_SPEC.md`
- `NIRI_PYPC_IMPLEMENTATION_GUIDE.md`
- `niri_pypc_code_review.md`
- `INITIAL_CODE_REVIEW.md`
- `INITIAL_CODE_REVIEW_v2.5.md`

### Code areas inspected directly

- `tools/normalize_ir.py`
- `tools/generate_types.py`
- `tools/verify_generated.py`
- `src/niri_pypc/types/codec.py`
- `src/niri_pypc/types/generated/reply.py`
- `src/niri_pypc/types/generated/models.py`
- `src/niri_pypc/api/client.py`
- `src/niri_pypc/api/event_stream.py`
- `src/niri_pypc/api/bundle.py`
- `src/niri_pypc/runtime/lifecycle.py`
- `src/niri_pypc/transport/connection.py`
- `src/niri_pypc/errors.py`
- `src/niri_pypc/config.py`
- exported schemas and normalized IR

### Direct runtime checks performed

#### A. Test suite behavior

- `pytest -q` passes: 112 tests passed, 3 skipped, with 89% coverage.

#### B. Generated verification behavior

- `python tools/verify_generated.py --ir schema/ir/niri-ipc-ir.json --generated-dir src/niri_pypc/types/generated`
  fails.

The diff includes cosmetic formatting changes, but it also corroborates semantically problematic generated output already reflected in the checked-in tree.

#### C. Direct protocol round-trip reproduction

This reply payload was validated directly against the attached code:

```python
from niri_pypc.types.generated.reply import Reply

raw = {
    "Ok": {
        "Outputs": [
            {
                "name": "HDMI-A-1",
                "make": "Dell",
                "model": "X",
                "serial": "123",
                "physical": None,
                "logical": None,
                "current_mode": None,
                "modes": [],
                "vrr_supported": False,
                "vrr_enabled": False,
                "vrr_mode": {"Fixed": {}},
                "transform": {"Normal": {}},
                "scale": 1.0,
                "variable_refresh_rate_supported": False,
            }
        ]
    }
}

reply = Reply.model_validate(raw)
print(reply)
print(reply.model_dump(mode="json"))
```

Observed behavior:

- validation succeeds as `OkReply(payload=Response(variant=OutputsResponse()))`
- serialization produces `{"Ok": "Outputs"}`

That is a protocol-fidelity failure. A valid payload is accepted and then discarded during re-serialization.

---

## 3. Synthesis of the prior reviews

The three earlier reviews do not carry equal weight.

### The strict review is substantially correct on the main problem

The findings in `niri_pypc_code_review.md` about lossy IR normalization, misclassified `anyOf` payloads, incorrect generated reply variants, broken round-trips, event-stream close issues, and dead version-check configuration are directionally correct and align with the attached code.

### `INITIAL_CODE_REVIEW.md` is broadly useful but partly overstates type/lint framing

`INITIAL_CODE_REVIEW.md` correctly identified several runtime and API concerns, especially around:
- brittle `unwrap_reply()` dispatch,
- silent exception swallowing,
- event-stream close sequencing,
- private lifecycle mutation,
- missing observability on overflow,
- type-safety limitations.

One finding from that review should be discarded: the schema exporter is present in the attached archive.

### `INITIAL_CODE_REVIEW_v2.5.md` underestimates severity

`INITIAL_CODE_REVIEW_v2.5.md` gets the architecture, layering, and many strengths right. It is useful on general quality and repository structure.

But it materially undercalls the generation problem by treating `verify-generated` drift as cosmetic and by concluding that the generated models are semantically correct. That conclusion does not survive direct inspection of the current IR and generated reply models.

---

## 4. Critical issues

These are the issues that most directly block correctness claims.

### C1. IR normalization is lossy for arrays, maps, tuple-like arrays, and nullable refs

**Files:**
- `tools/normalize_ir.py`
- `schema/ir/niri-ipc-ir.json`
- generated modules that consume the IR

**Why this matters**

The spec requires the IR to be a faithful, deterministic normalization of the exported schema. The current implementation collapses several schema shapes into overly generic forms, which changes the meaning of the upstream protocol.

**Direct code evidence**

In `tools/normalize_ir.py`, `canonical_type()` returns too early when `schema["type"]` exists:

- line 37 returns `_primitive_type(raw)` immediately,
- before checking `items`, `additionalProperties`, `prefixItems`, or more structured array/object cases.

That causes the following downstream degradations:

- arrays with typed `items` become `array<ref:Unknown>`
- maps with typed `additionalProperties` are not preserved when `type: object` is present
- tuple-like arrays with `prefixItems` are not preserved as structured tuples
- nullable arrays and refs lose fidelity depending on shape

**Confirmed examples from the attached IR**

- `Action.Spawn.command` is normalized as `array<ref:Unknown>` instead of `array<string>`.
- `Output.modes` is normalized as `array<ref:Unknown>` instead of `array<ref:Mode>`.
- `PickedColor.rgb` becomes `array<ref:Unknown>` instead of a typed float triple.
- `WindowLayout` tuple-like fields such as `tile_size`, `window_size`, and `window_offset_in_tile` degrade to generic arrays.
- `Output.physical_size` degrades to `option<array<ref:Unknown>>` instead of a typed pair.

**Impact**

This is not a typing nicety. It directly weakens schema fidelity and feeds incorrect information into generation.

**Fix**

Refactor `canonical_type()` so that schema shape analysis happens in the right precedence order:

1. `$ref`
2. nullable unions (`type: [T, null]`, `anyOf`, `oneOf` where relevant)
3. arrays with `items`
4. tuple-like arrays with `prefixItems`
5. maps with `additionalProperties`
6. plain objects / primitives

Unsupported tuple-like structures should hard-fail generation rather than silently degrade.

---

### C2. Variant classification mishandles nullable payload variants expressed as `anyOf[$ref, null]`

**Files:**
- `tools/normalize_ir.py`
- `schema/exported/reply.schema.json`
- `schema/ir/niri-ipc-ir.json`
- `src/niri_pypc/types/generated/reply.py`

**Why this matters**

Several `Response` variants in the reply schema carry nullable payloads. These are valid newtype-like externally tagged payload variants and should stay payload-bearing in the IR and generated code.

**Direct schema evidence**

The exported reply schema expresses the following variants as tagged object members whose value is `anyOf[$ref, null]`:

- `FocusedOutput`
- `FocusedWindow`
- `PickedWindow`
- `PickedColor`

**Current failure mode**

The classifier in `classify_variants()`:
- recognizes direct `$ref`
- recognizes inline `properties`
- recognizes raw `type`
- but does not correctly treat `anyOf[$ref, null]` as a payload-bearing newtype.

As a result, those variants fall through and are emitted as empty struct variants.

**Impact**

Nullable payload variants become payload-less classes, which is semantically wrong and leads directly to data loss.

**Fix**

Teach variant classification to recognize nullable newtype payloads explicitly, especially:
- `anyOf: [$ref, null]`
- `type: [primitive, null]`
- analogous cases that represent `option<T>` in the IR

---

### C3. Generated reply models are wrong for multiple variants

**Files:**
- `src/niri_pypc/types/generated/reply.py`
- `src/niri_pypc/types/generated/models.py`

**Why this matters**

Once the IR is wrong, the generated reply models become wrong. This is the clearest surface-level manifestation of the generator defect.

**Direct examples in the checked-in generated code**

The following classes are empty when they should carry payloads:

- `FocusedOutputResponse`
- `FocusedWindowResponse`
- `OutputsResponse`
- `PickedColorResponse`
- `PickedWindowResponse`

The following are present but with degraded payload typing:

- `LayersResponse.payload: list[Any]`
- `WindowsResponse.payload: list[Any]`
- `WorkspacesResponse.payload: list[Any]`

**Why this is wrong**

From the exported schema, these responses should carry:

- nullable `Output`
- nullable `Window`
- output map
- nullable `PickedColor`
- nullable `Window`
- typed lists of `LayerSurface`, `Window`, `Workspace`

**Impact**

The public protocol layer cannot be trusted to represent upstream replies faithfully.

**Fix**

Do not patch the generated files manually. Fix normalization and regeneration, then add regression tests that assert these exact reply shapes.

---

### C4. Valid replies can round-trip incorrectly and discard data

**Files:**
- `src/niri_pypc/types/generated/reply.py`
- `src/niri_pypc/types/codec.py`

**Why this matters**

A protocol model that accepts valid inbound data and then serializes back to a different, payload-less shape is not protocol-correct.

**Direct reproduction**

`Reply.model_validate({"Ok": {"Outputs": ...}}).model_dump(mode="json")` currently serializes as `{"Ok": "Outputs"}` in the attached code.

**Root cause**

This is the compounded result of:
- incorrect IR classification,
- incorrect generated reply variant shape,
- externally-tagged serializer doing exactly what the generated model shape tells it to do.

**Impact**

Round-trip invariants are broken for legitimate protocol payloads.

**Fix**

Treat this as the acceptance test for the generator repair. This specific reproduction should become a permanent regression test.

---

## 5. High-priority runtime and contract issues

These do not eclipse the generator problem, but they are still important correctness issues.

### H1. `verify-generated` is failing and must be treated as a correctness gate, not a cosmetic nuisance

**Files:**
- `tools/verify_generated.py`
- generated tree
- `tools/normalize_ir.py`
- `tools/generate_types.py`

**Why this matters**

The spec and implementation guide both make generated verification a required invariant. If generation from the current IR does not match the committed generated tree, the repository is out of contract.

**Current state**

Direct execution shows `verify_generated` fails.

Some diffs are formatting-only, but in this repository that is not the whole story because the generated outputs are already known to be semantically wrong in important areas.

**Fix**

- Fix normalization and generation first.
- Regenerate the tree.
- Ensure `verify-generated` passes.
- Make it a non-negotiable CI gate.

---

### H2. `NiriEventStream.close()` and reader-driven close are not safely coordinated

**Files:**
- `src/niri_pypc/api/event_stream.py`
- `src/niri_pypc/runtime/lifecycle.py`

**Why this matters**

The spec requires predictable, idempotent, cancellation-safe stream shutdown with no post-close event emission.

**Direct code evidence**

- `_close_from_reader()` transitions `READY -> CLOSING -> CLOSED`
- `close()` also transitions `READY -> CLOSING -> CLOSED`
- both paths inspect `is_terminal` before transitioning
- lifecycle transitions are lock-protected internally, but the outer close coordination is not

This creates a race window where two concurrent close paths can both pass the initial check and then contend on transitions.

**Impact**

The implementation is fragile around cancellation, reader termination, and explicit close. Even if the common path behaves, the state sequencing is not robust enough to claim strong lifecycle semantics.

**Fix**

Centralize shutdown into one internal close path, protected by a per-stream shutdown guard or lock. Reader termination should signal a single close routine rather than partially closing the stream itself.

---

### H3. Reader-side close drops the connection reference without closing the socket

**File:** `src/niri_pypc/api/event_stream.py`

**Direct code evidence**

`_close_from_reader()` does:

```python
self._connection = None
```

but never closes the underlying `UnixConnection` first.

**Why this matters**

That leaks responsibility for actual transport cleanup and is inconsistent with the explicit close path.

**Fix**

Reader-side close should close the connection if it still exists, then clear the reference.

---

### H4. Queue sentinel insertion during close can raise `asyncio.QueueFull`

**File:** `src/niri_pypc/api/event_stream.py`

**Direct code evidence**

Both `_close_from_reader()` and `close()` do:

```python
self._queue.put_nowait(_StreamClosed())
```

with no handling if the queue is already full.

**Why this matters**

A bounded event queue is explicitly part of the stream design. Close semantics must still work under full-queue conditions.

**Impact**

Close can raise unexpectedly instead of settling the stream cleanly.

**Fix**

Reserve capacity for the sentinel, drain one slot before enqueueing, or replace the queue/sentinel scheme with a close event plus stored terminal exception.

---

### H5. Connection loss is surfaced as `LifecycleError` instead of `TransportError`

**File:** `src/niri_pypc/api/event_stream.py`

**Direct code evidence**

When `next()` reads `_StreamClosed`, it raises `LifecycleError("Event stream has been closed")`.

The spec expectation is that connection loss should surface as `TransportError`; closure by caller and transport loss are not the same condition.

**Impact**

Callers cannot distinguish:
- a normal local close,
- a connection drop,
- a backpressure-triggered termination,
- a decode failure path.

**Fix**

Store the terminal cause and re-raise the correct exception from `next()`.

---

### H6. `__anext__()` does not honor async iterator close semantics

**File:** `src/niri_pypc/api/event_stream.py`

**Direct code evidence**

`__anext__()` simply does:

```python
event = await self.next()
return event
```

If the stream closes, `next()` raises `LifecycleError`; `__anext__()` never converts that to `StopAsyncIteration`.

**Why this matters**

The async iterator contract is part of the public API. `async for` should terminate naturally on stream closure.

**Fix**

Catch the internal close condition and raise `StopAsyncIteration` from `__anext__()`.

---

### H7. `event_read_timeout` is currently entangled with connection teardown behavior

**File:** `src/niri_pypc/api/event_stream.py`

**Direct code evidence**

The reader loop catches only `TransportError` around `read_frame()`. `UnixConnection.read_frame()` raises `NiriTimeoutError` on timeout. That timeout is not handled as a distinct non-terminal condition, so it falls through the broader cleanup behavior.

**Why this matters**

A configured read timeout should not necessarily mean "close the stream permanently". It should either:
- be a per-call `next()` timeout surface, or
- be very explicitly documented as an idle connection timeout policy.

Right now the behavior is surprising and harsher than the API contract suggests.

**Fix**

Separate idle read timeout policy from per-consumer `next(timeout=...)` timeout behavior. Prefer making idle gaps non-fatal unless explicitly configured otherwise.

---

### H8. Malformed events are silently swallowed

**File:** `src/niri_pypc/api/event_stream.py`

**Direct code evidence**

```python
except Exception:
    # Malformed event — skip it
    continue
```

**Why this matters**

Silent discard hides:
- protocol drift,
- generator/schema bugs,
- decode problems,
- unexpected payload changes.

This is especially problematic in a library whose core purpose is typed protocol correctness.

**Fix**

At minimum, log structured warnings. Prefer storing decode failures as terminal causes or surfacing them through an explicit error channel.

---

### H9. Overflow in `DROP_OLDEST` mode is not visible to callers

**File:** `src/niri_pypc/api/event_stream.py`

**Direct code evidence**

When the queue is full in `DROP_OLDEST` mode, the implementation drops one item and enqueues the new one without any warning or metric.

**Why this matters**

The concept explicitly says event overflow must not be silent.

**Fix**

Emit a warning log or expose a counter/hook. Silent lossy behavior undermines observability.

---

## 6. Medium-priority API and design issues

### M1. `NiriClient.connect()` drifts from the specified API shape

**File:** `src/niri_pypc/api/client.py`

**Direct code evidence**

`NiriClient.connect()` is currently a synchronous classmethod returning an instance directly.

The spec defines it as async.

**Why this matters**

This is contract drift and contributes to asymmetry with `NiriEventStream.connect()`, which is async. It also leads to mixed usage styles in the codebase and examples.

**Fix**

Pick one API shape and make it consistent with the spec and docs. Since the spec already chose async, aligning the implementation to that contract is the simplest option.

---

### M2. Lifecycle management is present but not used honestly throughout the API layer

**Files:**
- `src/niri_pypc/api/client.py`
- `src/niri_pypc/api/bundle.py`
- `src/niri_pypc/runtime/lifecycle.py`

**Why this matters**

A lifecycle manager only adds value if the API actually uses it to model real state transitions and invariants.

**Current issues**

- `NiriClient` largely uses lifecycle as a "closed" flag rather than a richer state machine.
- `NiriConnectionBundle` directly mutates `self._lifecycle._state = LifecycleState.READY`.

**Impact**

This bypasses the state machine’s own guarantees and weakens the correctness story.

**Fix**

Either:
- use the lifecycle manager consistently and expose any needed helper transitions properly, or
- simplify lifecycle usage where the richer state model is not actually needed.

Do not mutate private state directly.

---

### M3. `unwrap_reply()` depends on class-name prefixes rather than explicit dispatch

**File:** `src/niri_pypc/types/codec.py`

**Direct code evidence**

```python
cls_name = type(variant).__name__
if cls_name.startswith("Ok"):
...
if cls_name.startswith("Err"):
...
```

**Why this matters**

The reply envelope contract is explicit. Dispatching by class-name prefix is brittle and unnecessarily couples hand-written runtime logic to generator naming conventions.

**Fix**

Dispatch using explicit types or the generated mapping tables.

---

### M4. `encode_externally_tagged()` raises `DecodeError` for encode-time failures

**File:** `src/niri_pypc/types/codec.py`

**Direct code evidence**

When a variant class is unknown during encoding, the function raises `DecodeError`.

**Why this matters**

Encode-time failures are not decode failures. This weakens the clarity of the error taxonomy.

**Fix**

Introduce an encode-specific error or use `InternalError` if outbound unknown variants are considered impossible in correct code.

---

### M5. `DecodeError` does not centrally enforce bounded payload excerpts

**File:** `src/niri_pypc/errors.py`

**Why this matters**

The spec requires `DecodeError.raw_payload` to be bounded to 1024 characters. Right now truncation is handled ad hoc at call sites. That invites inconsistency.

**Fix**

Move truncation into the `DecodeError` constructor so the invariant is enforced centrally.

---

### M6. `strict_version_check` is dead configuration

**File:** `src/niri_pypc/config.py`

**Direct code evidence**

`strict_version_check: bool = True` exists in config, but no runtime path in the inspected code uses it.

**Why this matters**

Version mismatch policy is part of the concept, not an optional embellishment. A config field that suggests compatibility enforcement but is never applied is misleading API surface.

**Fix**

Either:
- implement a real version check flow consistent with the concept’s policy, or
- remove the setting until the feature exists.

---

### M7. `decode_externally_tagged()` is too trusting about dict key type and variant shape

**File:** `src/niri_pypc/types/codec.py`

**Direct code evidence**

```python
variant_name = cast(str, next(iter(data.keys())))
```

The function assumes JSON-like structure, but does not validate the key type explicitly.

**Why this matters**

This is minor compared to the generator defect, but it is still better practice to fail clearly and intentionally when the incoming shape is wrong.

**Fix**

Validate the key as `str` before use and raise `DecodeError` with a clear message if not.

---

## 7. Testing and verification gaps

### T1. Tests are too shallow where the generator is weakest

**Why this matters**

The current suite’s 89% coverage is respectable, but it does not validate the highest-risk surfaces strongly enough.

**Observed weak spots**

There is not enough schema-fidelity coverage for:
- nullable reply payload variants,
- typed maps and typed lists in replies,
- tuple-like arrays,
- richer struct payload shapes,
- generator regressions around `Outputs`, `Windows`, `Workspaces`, `Layers`, `PickedColor`, and `Focused*` variants.

**Fix**

Add golden fixtures and regression tests specifically targeting the known broken shapes.

---

### T2. Missing or under-covered transport and stream edge cases

**Why this matters**

The spec calls out malformed framing, partial reads, disconnects mid-frame, backpressure behaviors, and close semantics. Those are exactly the areas most likely to break in production.

**Recommended additions**

- queue-full-on-close behavior
- reader/caller concurrent close race
- malformed event propagation policy
- `FAIL_FAST` stream termination cause surfacing
- disconnect mid-frame
- invalid JSON in event stream
- reply round-trip regression tests for complex payloads

---

## 8. Tooling, packaging, and repository hygiene issues

### G1. Generated tree and repository artifacts are not cleanly maintained

**Observed issues**

The archive contains:
- `__pycache__` and `.pyc` files
- `tools/schema_exporter/target/` build artifacts

**Why this matters**

This adds noise to review, inflates archives, and increases the chance of stale artifacts confusing future work.

**Fix**

Add a `.gitignore` and remove cached/build outputs from the repository tree.

---

### G2. Repository hygiene currently weakens reproducibility claims

The project’s core value proposition includes deterministic generation and verification. Shipping cached Python/Rust build artifacts and a failing generated verification step weakens that claim even before runtime behavior is considered.

**Fix**

Make a clean-tree reproducibility pass part of CI and release preparation.

---

### G3. Documentation and code examples should be synchronized with the actual API shape

**Observed example drift**

The repository uses mixed connection styles across code and examples because `NiriClient.connect()` and `NiriEventStream.connect()` do not have symmetric shapes.

**Fix**

Once the API surface is finalized, update all examples to one clear, consistent style.

---

## 9. Issues that are improvements, not blockers

These are still worth addressing, but they are not the main reason the library is not ready.

- remove unnecessary `hasattr()` checks around `StreamWriter.close()` / `wait_closed()` in `UnixConnection.close()`
- move the lazy `ConfigError` import in `config.py` to top level unless there is a real dependency reason not to
- avoid swallowing secondary close exceptions silently in the bundle; aggregate or log them
- consider a clearer public export policy for `niri_pypc.types` if the surface becomes too noisy
- tighten generator formatting to eliminate avoidable drift in generated code output

---

## 10. Prioritized remediation order

This is the recommended order of work.

### Phase 1: Fix correctness at the generator boundary

1. Repair `tools/normalize_ir.py`
   - preserve typed arrays
   - preserve maps
   - preserve nullable refs
   - handle `prefixItems` correctly
   - ensure all top-level IR types are globally sorted

2. Regenerate all protocol types

3. Make `verify_generated` pass

4. Add protocol-fidelity regression tests for:
   - `Outputs`
   - `Windows`
   - `Workspaces`
   - `Layers`
   - `FocusedOutput`
   - `FocusedWindow`
   - `PickedColor`
   - `PickedWindow`
   - `Spawn.command`
   - `Output.modes`
   - tuple-like geometry fields

### Phase 2: Harden event-stream semantics

5. Unify close behavior through one internal shutdown routine
6. Preserve and surface terminal causes correctly
7. Stop silently swallowing malformed events
8. make sentinel/close behavior safe under full-queue conditions
9. return `StopAsyncIteration` correctly from `__anext__()`
10. separate idle-timeout policy from per-call read timeout semantics
11. close transport resources on reader-side shutdown
12. add visible overflow reporting in `DROP_OLDEST`

### Phase 3: Clean up API and taxonomy drift

13. align `NiriClient.connect()` with the intended contract
14. remove private lifecycle mutation from the bundle
15. replace class-name-prefix dispatch in `unwrap_reply()`
16. use the correct error class for encode failures
17. centralize payload excerpt truncation in `DecodeError`
18. implement or remove `strict_version_check`

### Phase 4: Reproducibility, docs, and repo hygiene

19. add `.gitignore`
20. remove cache/build artifacts
21. make the documented test workflow work from a clean checkout
22. synchronize README/examples with the final API
23. keep `verify-generated` and clean-tree checks green in CI

---

## 11. Acceptance criteria for declaring the library fixed

The library should not be declared corrected until all of the following are true:

1. `normalize_ir.py` preserves the known broken schema shapes.
2. Regenerated reply models correctly represent nullable payloads, typed maps, and typed lists.
3. The known reply round-trip bug is covered by a test and passes.
4. `verify_generated` passes with no diffs.
5. Event-stream close/error/overflow behavior is deterministic and covered by tests.
6. `__anext__()` terminates correctly on stream closure.
7. Terminal stream causes are distinguishable by callers.
8. The repository is clean of cache/build artifacts.
9. The test workflow is reproducible from a clean checkout using the documented setup.
10. The README and public API examples match the actual implementation.

---

## 12. Bottom line

`niri-pypc` is close to being a strong library, but the remaining work is not cosmetic. The current code has one major correctness defect and several important runtime semantics issues.

The most important conclusion from this final review is simple:

> Fix the schema/IR/generation pipeline first. Everything else should be sequenced after that.

Once that is corrected, the rest of the codebase looks very salvageable. The architecture is already good enough to support a clean remediation pass.

