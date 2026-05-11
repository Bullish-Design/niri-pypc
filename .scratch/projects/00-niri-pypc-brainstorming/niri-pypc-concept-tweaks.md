Here’s the revised change list I’d make to `NIRI_PYPC_CONCEPT.md` after combining the original review with the new `niri-state` split.

The short version: the document still has the right core shape, but it now needs two kinds of edits: boundary-hardening around `niri-state`, and a few protocol/runtime policy decisions that should be made explicit now rather than later.  

1. Add an explicit “ecosystem role” statement near the top.
   State that `niri-pypc` is the protocol/transport substrate for downstream libraries such as `niri-state`, and that it does not own a persistent, reduced, or canonical compositor state model. This sharpens the project identity without changing its core purpose.  

2. Expand the Non-Goals section to exclude state ownership.
   Add explicit non-goals for:

* maintaining an in-memory compositor state store
* reducers/selectors/snapshots
* replay/convergence/wait-until-style state logic
* reconciliation helpers built on top of raw events
  That follows directly from the new split, where `niri-pypc` delivers typed protocol events and `niri-state` applies them into derived state.  

3. Add a clear boundary: “typed protocol events” vs “derived state.”
   In the architecture and event sections, say this explicitly:

* `niri-pypc` owns event decoding, delivery, and wire-level correctness
* `niri-state` owns event application, reduction, snapshots, and selectors
  That is the most important new conceptual line introduced by the `niri-state` library.  

4. Tighten or rename the session abstraction.
   The current optional `NiriSession` concept is fine, but it now needs a narrower description so readers do not confuse it with a stateful store. I would either rename it to something like `NiriConnectionBundle`, or keep `NiriSession` but define it as a dual-channel connection convenience wrapper only. It should explicitly not maintain derived state, cached snapshots, reducers, or selectors.  

5. Add external dependency-direction rules.
   The current dependency rules are only internal. Add a short cross-library rule block:

* `niri-state -> niri-pypc`
* higher-level apps/libraries may depend on both
* `niri-pypc` must not depend on `niri-state` or downstream packages
  That protects the layering you are trying to establish.  

6. Fix the determinism/provenance contradiction in generation.
   Right now the doc says generation must be byte-for-byte deterministic, but it also suggests embedding a generation timestamp in IR metadata and `metadata.py`. Those conflict. Remove timestamps from committed/generated artifacts and keep only stable provenance such as upstream crate version, generator version, schema/IR hash, and optionally a source commit if it is part of the actual input.  

7. Add a runtime compatibility/version-mismatch policy.
   Because the whole library is pinned to one exact `niri-ipc` version, the concept should say what happens if the library talks to a compositor that does not match that protocol expectation. Decide now whether the policy is fail-fast, warn-and-continue, or best-effort with inbound unknown sentinels. The current pinning story is strong, but this operational case is still unspecified.  

8. Make supported-platform/runtime assumptions explicit.
   Add a compact compatibility section covering:

* supported Python versions
* Pydantic major version
* asyncio-only scope
* Linux/Unix-socket-only support
* whether sync API is a non-goal
  Those assumptions are implied by the design, but the concept should state them directly.  

9. Define config and socket-discovery policy.
   `config.py` is present in the repo layout, but the concept does not define what config owns. Add rules for:

* socket path discovery order
* env var precedence
* explicit overrides
* connect/read/write timeout config
* max-frame-size config
* event queue or buffer limits
  This will prevent API/runtime ambiguity later. 

10. Specify event-stream backpressure and buffering semantics.
    The document already treats event streaming as a first-class runtime concern, but it should say what happens when consumers are slow:

* bounded vs unbounded buffering
* block, drop, or close behavior
* ordering guarantees
* async iterator support vs `next()`
* close/cancel behavior during reads
  This is especially important now that state reduction is moving into `niri-state`; `niri-pypc` needs a crisp delivery contract.  

11. Strengthen the codegen contract a bit more.
    The IR idea is good. I would add:

* explicit IR schema versioning
* stable sort/order rules
* naming normalization and reserved-word handling
* unsupported-shape behavior must hard-fail
* clarify exactly what is committed to git: exporter, schema, IR, generated code, fixtures
  That makes the “pinned, reproducible, reviewable” story more concrete. 

12. Expand the error model to separate remote semantic failures from local decode/transport failures.
    Right now the taxonomy is good but still slightly too compressed. Add a distinction between:

* transport failure
* decode/protocol-shape failure
* remote handled/semantic error from Niri
* local config/lifecycle error
  That will make higher-level consumers, including `niri-state`, much easier to write correctly. 

13. Add concurrency/task-safety rules for public objects.
    Say whether these are allowed:

* multiple concurrent `request()` calls
* closing from a different task
* multiple consumers on one event stream
* sharing a client/session across tasks
  Even simple rules here will prevent accidental misuse.  

14. Update the testing section to explicitly exclude state/reducer tests.
    Keep the existing type, transport, API, integration, and live tests, but add one line saying reducer, selector, replay, convergence, and state-store tests belong in `niri-state`, not `niri-pypc`. That reinforces the new library boundary without changing the existing test plan much.  

15. Update the documentation plan and README guidance.
    Add README language that says:

* `niri-pypc` is the pinned protocol/runtime layer
* event delivery is raw typed protocol delivery, not reduced state
* use `niri-state` for a live derived compositor state model
  That will stop users from expecting the IPC package to behave like a state engine.  

16. Clean up a couple of wording/consistency issues.
    I would also fix:

* the typo `niri-ipc = =<PINNED_VERSION>`
* the mixed “`devenv.sh` vs `devenv.nix` canonical entrypoint” wording
* whether helper modules under `types/` are public API or internal-only
  Those are smaller, but worth cleaning up while you revise the doc.  

If I were prioritizing the edits, I’d do them in this order:

1. add the `niri-state` boundary and new non-goals
2. tighten `NiriSession`
3. fix deterministic generation metadata
4. add version-mismatch/runtime compatibility policy
5. specify event-stream backpressure and config policy
6. update tests/docs/dependency rules

If you want, I can turn this into a section-by-section patch plan against the current `NIRI_PYPC_CONCEPT.md`.
