Absolutely. Here is the implementation-oriented version: exact edit order, suggested commit sequence, what to change in each file, and what must pass before moving on.

This is designed so the agent can execute it mechanically without needing to re-derive the architecture.

---

# Recommended commit sequence

Use small, reviewable commits, but allow temporary breakage between commits on the branch. The final branch should only be considered complete once the full test suite and visible demo pass again.

## Commit 01 — Add the new handwritten protocol base layer

### Files

1. `src/niri_pypc/types/base.py` **(new)**
2. `src/niri_pypc/types/__init__.py`
3. `tests/types/test_base_runtime.py` **(new)**

### Goal

Introduce the shared runtime abstractions before touching code generation.

### Edit order

1. Create `types/base.py`
2. Export the new symbols in `types/__init__.py`
3. Add tiny handwritten tests using fake local models

### Required code

Use the `ProtocolModel`, `ProtocolVariant`, `UnknownEvent`, and `ExternallyTaggedEnum` structure from the prior plan.

### Must verify

Run only:

```bash
pytest -q tests/types/test_base_runtime.py
```

### Commit message

```text
add protocol base layer with RootModel enum runtime
```

---

## Commit 02 — Replace the codec with a metadata-driven codec

### Files

1. `src/niri_pypc/types/codec.py`
2. `tests/types/test_codec_contract.py` **(new)**

### Goal

Delete all field-count/field-name inference.

### Edit order

1. Replace `codec.py` completely
2. Add contract tests for:

   * unit
   * newtype
   * zero-field struct
   * invalid shape failures
   * unknown event behavior

### Important rule

Do **not** re-add reply unwrapping here.

### Must verify

Run:

```bash
pytest -q tests/types/test_codec_contract.py tests/types/test_base_runtime.py
```

### Commit message

```text
rewrite externally tagged codec to use explicit variant metadata
```

---

## Commit 03 — Refactor generator internals to support the new architecture

### Files

1. `tools/generate_types.py`

### Goal

Teach the generator the three distinct cases:

* plain struct -> `ProtocolModel`
* mixed externally tagged enum -> `ProtocolVariant` + `ExternallyTaggedEnum`
* all-unit enum -> `StrEnum`

### Edit order inside `generate_types.py`

1. Add imports and generator support for:

   * `ProtocolModel`
   * `ProtocolVariant`
   * `ExternallyTaggedEnum`
   * `StrEnum`
2. Add helpers:

   * `is_all_unit_enum(...)`
   * `variant_class_name(...)`
   * `safe_enum_member_name(...)`
3. Rewrite struct generation
4. Rewrite variant generation so `__niri_variant_kind__` is always emitted
5. Add all-unit enum generation via `StrEnum`
6. Add mixed enum wrapper generation via `RootModel`
7. Generate `Reply.unwrap()`
8. Delete any generator logic that emits:

   * `.variant` field wrappers
   * repeated `@model_validator`
   * repeated `@model_serializer`
   * `UnknownReply`

### Critical generator invariants

For every enum variant emitted:

* wire name preserved exactly
* variant kind preserved exactly
* zero-field struct stays `"struct"`, never collapsed to `"unit"`

### Must verify

Regenerate but do not worry about global test failures yet:

```bash
python tools/generate_types.py
```

Then inspect these files manually:

```bash
sed -n '1,220p' src/niri_pypc/types/generated/action.py
sed -n '1,220p' src/niri_pypc/types/generated/request.py
sed -n '1,220p' src/niri_pypc/types/generated/reply.py
sed -n '1,260p' src/niri_pypc/types/generated/models.py
sed -n '1,220p' src/niri_pypc/types/generated/event.py
```

### Manual checks

Confirm all of these are true:

* `ToggleOverviewAction.__niri_variant_kind__ == "struct"`
* `VersionRequest.__niri_variant_kind__ == "unit"`
* `ErrReply.__niri_variant_kind__ == "newtype"`
* `Action`, `Request`, `Reply`, `Response`, `Event` inherit from `ExternallyTaggedEnum`
* helper all-unit enums are `StrEnum`
* no generated `.variant` wrappers remain
* `UnknownReply` is gone

### Commit message

```text
rewrite type generator for RootModel enums and explicit variant kinds
```

---

## Commit 04 — Regenerate types and add generated-contract tests

### Files

1. all files under `src/niri_pypc/types/generated/`
2. `tests/types/test_generated_contract.py` **(new)**
3. `tools/verify_generated.py` if needed

### Goal

Lock down semantic invariants from generated output.

### Edit order

1. Regenerate all types
2. Add representative semantic tests
3. Update `verify_generated.py` only if needed to handle the new output layout

### Required tests

Add tests for:

* representative variant kind preservation
* representative wrappers are `RootModel`
* representative helper enum is `StrEnum`
* `UnknownReply` absent

### Example checks

```python
assert ToggleOverviewAction.__niri_variant_kind__ == "struct"
assert VersionRequest.__niri_variant_kind__ == "unit"
assert ErrReply.__niri_variant_kind__ == "newtype"
assert issubclass(Action, RootModel)
assert Transform.NORMAL.value == "Normal"
```

### Must verify

Run:

```bash
python tools/verify_generated.py
pytest -q tests/types/test_generated_contract.py
```

### Commit message

```text
regenerate types and add generator contract coverage
```

---

## Commit 05 — Rewrite all type roundtrip tests to the new API

### Files

1. `tests/types/test_roundtrip.py`
2. `tests/types/test_reply_roundtrip.py`
3. `tests/types/test_unknown_variants.py`
4. `tests/types/test_generated_shapes.py`
5. any other type test using `.variant`

### Goal

Move tests from `.variant` wrappers to `.root` wrappers and direct payload assertions.

### Edit order

1. Replace all `Request(variant=...)` with `Request(root=...)`
2. Replace all `.variant` reads with `.root`
3. Delete `UnknownReply` tests
4. Add the explicit unit/newtype/zero-field-struct distinction tests
5. Add `Reply.unwrap()` tests

### Must verify

Run:

```bash
pytest -q tests/types
```

### Commit message

```text
rewrite generated type tests to RootModel contract
```

---

## Commit 06 — Refactor the client to use JSON model entrypoints and return real payloads

### Files

1. `src/niri_pypc/api/client.py`
2. `src/niri_pypc/transport/framing.py` or delete it
3. `tests/api/test_client.py`

### Goal

Transport should be bytes + newline only. The client should:

* wrap request variant in `Request(root=...)`
* serialize with `model_dump_json()`
* parse replies with `Reply.model_validate_json(...)`
* return unwrapped response payload

### Edit order

1. Simplify or delete `framing.py`
2. Rewrite `NiriClient.request()`
3. Update tests to expect direct response variants

### New public contract

This should now be true:

```python
result = await client.request(VersionRequest())
assert isinstance(result, VersionResponse)
assert result.payload == "..."
```

Not:

```python
result.variant.payload
```

### Required client test additions

Add a specific action wire-shape test for zero-field struct actions.

### Must verify

Run:

```bash
pytest -q tests/api/test_client.py
```

### Commit message

```text
simplify client transport edges and return unwrapped responses
```

---

## Commit 07 — Refactor event stream bootstrap into an explicit handshake

### Files

1. `src/niri_pypc/api/event_stream.py`
2. `tests/api/test_event_stream.py`

### Goal

The stream must:

1. connect
2. send `EventStream`
3. read one reply frame
4. parse as `Reply`
5. require `HandledResponse`
6. only then start the event reader

### Edit order

1. Add `_bootstrap()`
2. Call it from `connect()`
3. Update reader to parse only `Event`
4. Rewrite event stream tests to include bootstrap reply before any event

### Mandatory tests

* handshake success
* handshake error reply
* handshake wrong reply type
* first yielded item is a real event
* no bootstrap ack appears as `UnknownEvent("Ok")`

The demo error report specifically calls out that misclassification problem. 

### Must verify

Run:

```bash
pytest -q tests/api/test_event_stream.py
```

### Commit message

```text
make event stream handshake explicit and event-only after bootstrap
```

---

## Commit 08 — Rewrite fake socket helpers and shared fixtures

### Files

1. `tests/helpers/fake_niri_socket.py`
2. `tests/conftest.py`
3. `tests/api/test_bundle.py`
4. any fixture helper that simulates streaming

### Goal

All helpers must simulate the correct protocol, especially the event stream ack.

### Edit order

1. Add explicit `bootstrap_reply` support
2. Update event servers to send reply first, then events
3. Update bundle tests and any other users of fake streaming

### Required negative-path tests

Add cases for:

* EOF before handshake reply
* malformed bootstrap reply
* bootstrap `Err`
* wrong bootstrap response type

### Must verify

Run:

```bash
pytest -q tests/api/test_bundle.py tests/api/test_event_stream.py
```

### Commit message

```text
fix fake socket fixtures to model real stream bootstrap protocol
```

---

## Commit 09 — Update all runtime and integration tests to remove `.variant`

### Files

Search all of:

* `tests/api/`
* `tests/integration/`
* `tests/live/`
* `demo/`

Use:

```bash
rg -n '\.variant|variant=' tests demo src
```

### Goal

Kill the old wrapper mental model everywhere.

### Edit order

1. Replace `.variant.payload` with direct response payload access
2. Replace wrapper construction with `root=...`
3. Remove old helper assumptions in tests
4. Re-run grep until matches are gone or justified

### Must verify

Run targeted groups as they stabilize:

```bash
pytest -q tests/integration
pytest -q tests/live/test_live.py
```

### Commit message

```text
remove old variant wrapper usage across runtime and integration tests
```

---

## Commit 10 — Refactor the demo to the new public API and make it more deterministic

### Files

1. `demo/visual_demo.py`

### Goal

The demo should:

* stop using `.variant`
* stop logging handshake ack as unknown event
* stop depending on blind sleeps where state polling is better
* prefer explicit overview actions

### Edit order

1. Update typed request helper to expect direct response variants
2. Update action construction to `Action(root=...)`
3. Replace `ToggleOverview` choreography with explicit open/close actions where possible
4. Add small polling helpers for:

   * window count
   * overview state
   * workspace focus

### Must verify

Run:

```bash
python demo/visual_demo.py --help
pytest -q tests/integration/test_nested_niri_events.py
```

If practical, also run the visible demo locally after this commit.

### Commit message

```text
refactor visual demo to new response API and deterministic state waits
```

---

## Commit 11 — Refactor nested harness readiness and manifest strictness

### Files

1. `tests/helpers/nested_niri.py`
2. harness-related tests

### Goal

The harness should declare readiness only after a real IPC request succeeds.

### Edit order

1. Add strict local fixture base model:

   * `frozen=True`
   * `strict=True`
   * `extra="forbid"`
2. Update all scenario manifest models to inherit from it
3. Add protocol readiness probe via `VersionRequest`
4. Keep settle delay only as optional polish, not correctness

### Required tests

* extra YAML keys rejected
* readiness probe retries
* readiness probe fails cleanly if socket exists but IPC is not yet live

### Must verify

Run:

```bash
pytest -q tests/helpers
pytest -q tests/integration/test_nested_niri_basic.py tests/integration/test_nested_niri_events.py
```

### Commit message

```text
make nested harness readiness depend on live IPC and strict manifests
```

---

## Commit 12 — Remove dead architecture and clean docs/comments

### Files

Search broadly:

* `src/`
* `tests/`
* `demo/`
* README/docs/spec notes if present

### Goal

Delete every remaining explanation or helper that describes the old architecture.

### Delete or rewrite

* `unwrap_reply()` helper if still present anywhere
* comments describing wrappers as `BaseModel` with `.variant`
* comments/docs saying event streams start sending events immediately after request
* compatibility comments for old action encoding

### Must verify

Run:

```bash
rg -n '\.variant|variant=|UnknownReply|populate_by_name|unwrap_reply' src tests demo
```

Anything left should be intentional and reviewed.

### Commit message

```text
remove dead wrapper architecture and outdated protocol assumptions
```

---

## Commit 13 — Final verification and polish

### Goal

Make the branch releasable.

### Full verification

Run all of:

```bash
python tools/generate_types.py
python tools/verify_generated.py
ruff check .
ruff format --check .
pytest -q
```

Then run the visible demo again:

```bash
NIRI_PYPC_ALLOW_VISIBLE_NESTED=1 python demo/visual_demo.py --wire-log
```

### Expected final visible-demo behavior

* no initial `UnknownEvent` containing `Ok` / `Handled`
* no parser errors for zero-field struct actions
* normal command/query flow still works
* event stream still works
* teardown still clean

### Commit message

```text
finalize protocol model refactor and validate demo/runtime behavior
```

---

# Exact per-file edit order

If the agent wants a strict file-by-file walk, use this order:

## Handwritten runtime first

1. `src/niri_pypc/types/base.py`
2. `src/niri_pypc/types/codec.py`
3. `src/niri_pypc/types/__init__.py`

## Generator next

4. `tools/generate_types.py`
5. regenerate `src/niri_pypc/types/generated/*`
6. `tools/verify_generated.py`

## Type tests next

7. `tests/types/test_base_runtime.py`
8. `tests/types/test_codec_contract.py`
9. `tests/types/test_generated_contract.py`
10. all existing `tests/types/*`

## Runtime API next

11. `src/niri_pypc/api/client.py`
12. `src/niri_pypc/api/event_stream.py`
13. `src/niri_pypc/transport/framing.py` or delete it

## Runtime tests and fixtures next

14. `tests/helpers/fake_niri_socket.py`
15. `tests/conftest.py`
16. `tests/api/test_client.py`
17. `tests/api/test_event_stream.py`
18. `tests/api/test_bundle.py`

## Integration and demo next

19. `tests/integration/*`
20. `tests/live/*`
21. `demo/visual_demo.py`

## Harness last

22. `tests/helpers/nested_niri.py`
23. harness tests

## Cleanup last

24. README/docs/spec notes/comments
25. final grep cleanup

---

# Suggested stop points for review

Use these as hard review gates before proceeding.

## Gate A

After Commit 02:

* base runtime and codec tests pass

## Gate B

After Commit 04:

* generated output shape is visibly correct
* generator contract tests pass

## Gate C

After Commit 07:

* event stream handshake is fixed in both code and fixtures

## Gate D

After Commit 11:

* all runtime/integration tests are green

## Gate E

After Commit 13:

* visible demo no longer shows the two failures from the report 

---

# agent checklist

This is the short version they can keep beside them while implementing.

## Do first

* add `types/base.py`
* rewrite `codec.py`
* rewrite generator
* regenerate types

## Then fix all tests that encode the old architecture

* `.variant` -> `.root` for wrappers
* client returns direct response variants
* stream fixtures must send bootstrap reply first

## Then fix runtime

* client JSON edges
* event stream bootstrap
* fake sockets
* bundle/integration/demo

## Then harden

* strict harness manifest models
* readiness probe via `VersionRequest`
* delete dead comments/helpers/docs

## Never do

* patch generated files manually as the real fix
* preserve backwards compatibility
* reintroduce field-shape heuristics
* keep the old event-stream fixture behavior

---

# One practical rule for the agent

Whenever you are unsure how something should serialize, ask this question:

> Is this a `unit`, `newtype`, or `struct` variant in the IR?

Then serialize exactly from that answer, never from the Python field layout.

That single rule is the center of the whole refactor.

If you want, I can also turn this into a GitHub-style task list with checkboxes and acceptance criteria under each task.
