# niri-pypc code review

Repository reviewed from `niri-pypc.zip` against the attached concept/spec/implementation docs.

## Headline

The project has a solid intended shape, but it is not ready to be called protocol-correct yet. The single biggest problem is that the schema→IR→generation pipeline is losing protocol information in multiple places, which means several generated models are not faithful to the upstream `niri-ipc 25.11` schema.

## Strong parts

- Good separation between generated protocol models and hand-written runtime/client code.
- Transport/framing modules are small and readable.
- Error hierarchy exists and is mostly sensible.
- Event stream and command client are split cleanly.
- The codebase is easy to navigate.

## Critical findings

1. **IR normalization is fundamentally lossy for arrays/maps/nullable refs**
   - `tools/normalize_ir.py:28-61`
   - `canonical_type()` returns too early on `type`, before looking at `items`, `additionalProperties`, or tuple arrays.
   - Effects:
     - `SpawnAction.command` becomes `list[Any]` instead of `list[str]`
     - `Output.modes` becomes `list[Any]` instead of `list[Mode]`
     - tuple-like geometry fields become `list[Any]`
     - map-like payloads are not preserved correctly

2. **Variant classification mishandles `anyOf` payloads**
   - `tools/normalize_ir.py:92-162`
   - Payload shapes like `anyOf[$ref, null]` are not recognized as newtypes and fall through as empty struct variants.
   - This breaks nullable payload variants such as `FocusedOutput`, `FocusedWindow`, `PickedColor`, `PickedWindow`.

3. **Generated reply models are incorrect for several variants**
   - `src/niri_pypc/types/generated/reply.py:70-119`
   - `FocusedOutputResponse`, `FocusedWindowResponse`, `OutputsResponse`, `PickedColorResponse`, and `PickedWindowResponse` are empty classes when they should carry payloads.
   - `LayersResponse`, `WindowsResponse`, and `WorkspacesResponse` degrade to `list[Any]`.

4. **Some replies round-trip incorrectly and discard data**
   - Caused by the two issues above.
   - Example observed locally:
     - `Reply.model_validate({"Ok": {"Outputs": {...}}}).model_dump(mode="json")`
     - re-serializes as `{"Ok": "Outputs"}`
   - That is a protocol fidelity failure, not just weak typing.

5. **`verify_generated` fails on the checked-in tree**
   - Running `python tools/verify_generated.py --ir schema/ir/niri-ipc-ir.json --generated-dir src/niri_pypc/types/generated` failed.
   - That means committed generated artifacts are not in sync with the current generator/IR.

6. **`NiriEventStream.close()` can raise `asyncio.QueueFull`**
   - `src/niri_pypc/api/event_stream.py:132-135, 213-214`
   - The code pushes a close sentinel with `put_nowait()` and does not handle a full queue.
   - Observed locally with `event_queue_capacity=1`: `await stream.close()` raised `QueueFull`.

7. **Reader-side close drops the connection reference without closing the socket**
   - `src/niri_pypc/api/event_stream.py:128-136`
   - `_close_from_reader()` sets `self._connection = None` but never closes it.

8. **`event_read_timeout` currently closes the whole stream on idle gaps**
   - `src/niri_pypc/api/event_stream.py:93-98, 123-126`
   - `read_frame()` can raise `NiriTimeoutError`, but `_run_reader()` only handles `TransportError` before falling into broad cleanup.
   - Observed locally: setting `event_read_timeout=0.05` caused the stream to move to `CLOSED` before the first delayed event arrived.

9. **Malformed events are silently swallowed**
   - `src/niri_pypc/api/event_stream.py:100-105`
   - Broad `except Exception: continue` hides protocol drift and decode bugs.

10. **Connection loss is surfaced as `LifecycleError`, not `TransportError`**
   - `src/niri_pypc/api/event_stream.py:176-181`
   - The spec says `next()` should raise `TransportError` when the connection is lost.

11. **`__anext__` does not honor the advertised iterator contract**
   - `src/niri_pypc/api/event_stream.py:195-197`
   - The spec says `__anext__` should raise `StopAsyncIteration` on stream close.
   - Current implementation just delegates to `next()` and propagates its exceptions.

12. **Lifecycle manager is present but not truly integrated in the client**
   - `src/niri_pypc/api/client.py:25-27, 71-76, 109-110`
   - `NiriClient` never transitions through `CONNECTING`/`READY` and uses the lifecycle manager mostly as a “closed” flag.

13. **Bundle breaks encapsulation by mutating private lifecycle state directly**
   - `src/niri_pypc/api/bundle.py:26-27`
   - `self._lifecycle._state = LifecycleState.READY` bypasses the state machine entirely.

14. **`NiriClient.connect()` API shape drifts from the spec**
   - `src/niri_pypc/api/client.py:29-42`
   - The spec defines it as `async def connect(...)`; the implementation is synchronous.
   - This also creates an odd asymmetry with `NiriEventStream.connect()` and the README examples.

15. **`strict_version_check` is dead configuration**
   - Declared in `src/niri_pypc/config.py:26`
   - No runtime usage found.
   - The concept/spec explicitly frame version-mismatch handling as part of the library contract.

16. **`encode_externally_tagged()` raises the wrong exception class**
   - `src/niri_pypc/types/codec.py:99-103`
   - Encode-time errors should not be raised as `DecodeError`.

17. **`unwrap_reply()` relies on class-name prefixes**
   - `src/niri_pypc/types/codec.py:141-151`
   - `startswith("Ok")` / `startswith("Err")` is brittle and couples handwritten runtime logic to generator naming conventions.

18. **`DecodeError` does not enforce payload truncation centrally**
   - `src/niri_pypc/errors.py:33-44`
   - The spec says raw payload excerpts are bounded to 1024 chars. Right now that invariant depends on every call site remembering to truncate.

19. **IR top-level type ordering does not match the spec**
   - `tools/normalize_ir.py:294-309`
   - The spec says all top-level types are sorted alphabetically by name.
   - The implementation builds `types` as `enums + structs`, which is not globally sorted.

20. **Test suite is too shallow where the generator is weakest**
   - Missing spec-called golden tests/fixtures.
   - Current roundtrip tests mainly cover easy unit/simple cases and do not exercise the broken reply payload shapes.

## Style and hygiene findings

- The zip contains `__pycache__/`, `.pyc`, and `tools/schema_exporter/target/` artifacts.
- No `.gitignore` was present in the archive.
- The generated tree is not in sync with the generator.
- README examples are inconsistent (`NiriClient.connect()` is used without `await`, `NiriEventStream.connect()` with `await`).

## Recommended fix order

1. Fix `normalize_ir.py` first.
2. Regenerate types and add schema-fidelity regression tests.
3. Fix `Reply`/`Response` correctness and verify round-trips for complex payload variants.
4. Repair event-stream shutdown, queue-full handling, and timeout semantics.
5. Make lifecycle usage honest: either fully use it or simplify it.
6. Implement or remove `strict_version_check`.
7. Clean repository hygiene (`.gitignore`, remove build/cache artifacts).
8. Make `verify_generated` green and keep it green in CI.

## Bottom line

This project has a promising architecture, but the generator pipeline is currently the dominant risk and must be treated as the top priority. Until the schema fidelity issues are fixed, the library cannot reliably claim that its generated protocol layer matches the pinned upstream contract.
