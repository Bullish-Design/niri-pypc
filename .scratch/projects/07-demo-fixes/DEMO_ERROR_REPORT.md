# DEMO_ERROR_REPORT

## Scope

This report analyzes the `--wire-log` run output from:

```bash
NIRI_PYPC_ALLOW_VISIBLE_NESTED=1 python demo/visual_demo.py --wire-log
```

Goal: explain exactly what is happening in the demo, identify confirmed issues vs expected behavior, and capture investigation targets.

---

## Executive Summary

The demo is partially successful:

- Visible nested `niri` starts correctly.
- IPC command requests (`Version`, `Outputs`, `Workspaces`, `Windows`, etc.) work.
- Event stream is active and delivering state/event updates.
- `SpawnSh` actions work and create windows.
- Some action requests consistently fail with `RemoteError: Compositor error: error parsing request`.

Two likely protocol-level problems are visible:

1. The initial event-stream acknowledgment appears to be processed as an event (`UnknownEvent` with `variant_name: "Ok"` and `raw_payload: "Handled"`), indicating stream-bootstrap reply handling is incorrect.
2. Many unit-style actions are being serialized as string payloads and rejected, while structured actions with object payloads succeed.

---

## Timeline of the Observed Run

## 1) Startup and Initial State

Evidence:

- `[demo] started visible nested niri: socket=/run/user/1000/niri.wayland-2.78733.sock, pid=78733, pgid=78733`

Interpretation:

- Nested compositor launch succeeded.
- Safety controls and process lifecycle are functioning (startup and eventual teardown both happen cleanly).

## 2) First Command Request and Event Stream Activity

Evidence:

- Outgoing command: `[wire][out] WindowsRequest: {}`
- Immediately followed by: `[wire][in] UnknownEvent: {"raw_payload": "Handled", "variant_name": "Ok"}`
- Then expected stream bootstrap events:
  - `WorkspacesChangedEvent`
  - `WindowsChangedEvent`
  - `KeyboardLayoutsChangedEvent`
  - `OverviewOpenedOrClosedEvent`
  - `ConfigLoadedEvent`
- Then command reply appears: `[wire][in] WindowsResponse: {"payload": []}`

Interpretation:

- The `UnknownEvent` payload strongly resembles `Reply::Ok(Response::Handled)` (the standard ack after event stream request), but it is logged as an event.
- This suggests event-stream setup currently does not explicitly read/validate the `EventStream` ack before entering event decode mode.

## 3) Window Spawning Works

Evidence:

- Outgoing action:
  - `ActionRequest: {"payload": {"SpawnSh": {"command": "..."}}}`
- Incoming reply:
  - `HandledResponse: {}`
- Followed by window/workspace events:
  - `WindowOpenedOrChangedEvent` for window IDs `2`, later `3`, `4`
  - `WorkspaceActiveWindowChangedEvent`
- Snapshot confirms window count increase:
  - `windows=3`

Interpretation:

- Action dispatch path is operational for `SpawnSh`.
- Event stream and state snapshots are coherent with spawned windows.

## 4) Overview and Multiple Unit Actions Fail Parsing

Evidence:

- Outgoing:
  - `ActionRequest: {"payload": "ToggleOverview"}`
  - `ActionRequest: {"payload": "FocusWindowDown"}`
  - `ActionRequest: {"payload": "FocusWindowUp"}`
  - `ActionRequest: {"payload": "MoveWindowDown"}`
  - `ActionRequest: {"payload": "MoveWindowUp"}`
  - `ActionRequest: {"payload": "FocusWorkspaceDown"}`
  - `ActionRequest: {"payload": "FocusWorkspaceUp"}`
  - `ActionRequest: {"payload": "MoveColumnRight"}`
  - `ActionRequest: {"payload": "MoveColumnLeft"}`
- Incoming failure each time:
  - `RemoteError: Compositor error: error parsing request`

Interpretation:

- These unit actions are rejected at request parse time by compositor IPC parsing.
- Failure occurs before semantics/state checks (i.e., parser rejected payload shape).

## 5) Structured Actions with Arguments Succeed

Evidence:

- Outgoing:
  - `ActionRequest: {"payload": {"MoveWindowToWorkspaceDown": {"focus": true}}}`
  - `ActionRequest: {"payload": {"MoveWindowToWorkspaceUp": {"focus": false}}}`
- Incoming:
  - `HandledResponse: {}`
- Follow-up events show workspace/window changes.

Interpretation:

- The request/action envelope itself is valid.
- At least some action variants are encoded in a format compositor accepts.
- Rejections are concentrated in unit-variant action encoding.

## 6) Snapshot Stability and Final State

Evidence (repeated snapshots):

- `version=25.11 (Nixpkgs)`
- `outputs=1`
- `workspaces=3`
- `windows=3`
- `layouts=['English (US)']`
- `focused_output=winit`
- `focused_window=None`
- `errors=10`

Interpretation:

- Library requests and decoding are stable after action failures.
- Demo loop remains alive and failure-tolerant.
- `focused_window=None` is possible after workspace/window moves and is not necessarily an error.

---

## Confirmed Issues

## Issue A: EventStream ACK appears misclassified as event

Observed symptom:

- `UnknownEvent` containing `variant_name: "Ok"`, `raw_payload: "Handled"`.

Why this is a problem:

- `Ok(Handled)` is a reply envelope for event-stream startup, not an event payload.
- Indicates stream bootstrap reply likely is not explicitly consumed and validated prior to event decode loop.

Impact:

- Confusing logs.
- Potentially masks stream bootstrap failures.
- Can produce subtle ordering/diagnostic noise.

## Issue B: Unit action wire representation likely incompatible with runtime parser

Observed symptom:

- Unit actions sent as string payload form (e.g., `"FocusWindowDown"`) fail with parser error.
- Structured actions with object payloads (e.g., `{"MoveWindowToWorkspaceDown": {"focus": true}}`) succeed.

Why this is a problem:

- Demonstrates inconsistent action compatibility in current serializer/runtime combination.
- Prevents showcasing many movement/focus actions in demo.

Impact:

- High noise in demo (`errors=10` in sample run).
- Incomplete action showcase.

---

## Non-Issues / Expected Behavior

- Spawning nested windows via `SpawnSh` works correctly.
- Event stream emits sensible updates tied to spawned windows.
- Snapshot requests decode correctly and repeatedly.
- Graceful Ctrl+C teardown works (`nested niri stopped`).

---

## Most Likely Root Causes

## Root Cause 1: Stream bootstrap handling gap

Hypothesis:

- Event stream client should read first post-`EventStreamRequest` frame as `Reply` (`Ok(Handled)`), then switch to event decoding.
- Current path appears to decode that ack through event codec path and surfaces as `UnknownEvent`.

## Root Cause 2: Unit action serialization mismatch

Hypothesis:

- Current action encoder emits unit variants in scalar/string form.
- This runtime/compositor expects a different representation for some/all unit action variants (likely object-tagged form), or has compatibility differences for these variants in this build.

---

## Suggested Investigation Steps (For Later)

1. Add a raw frame tap around event-stream connect handshake.
2. Confirm first frame after `EventStreamRequest` is parsed as `Reply` before event loop starts.
3. For failing unit actions, send equivalent action through `niri msg --json action ...` and capture exact JSON shape accepted by compositor.
4. Compare accepted `niri msg` JSON shape with `model_dump(mode="json")` output from generated action model.
5. Add temporary compatibility retry in demo for unit actions (string form -> object-tag form) to verify serializer mismatch hypothesis quickly.
6. If confirmed, fix encoder behavior for unit action variants (or add runtime-compat mode), then remove retry workaround.

---

## Current Demo Reliability Assessment

- Command/data-plane reliability: **High**
- Event stream reliability: **Moderate-High** (with bootstrap handling caveat)
- Action showcase reliability: **Low-Moderate** (blocked by unit action parse failures)
- Safety/teardown reliability: **High**

---

## Conclusion

The demo is not fundamentally broken: nested compositor control, state queries, event stream, and process cleanup work.

The primary defects are protocol-shape/handshake details:

- event-stream ack handling should be explicit,
- unit action encoding appears incompatible with this compositor runtime for multiple actions.

These are actionable and isolated; once fixed, the demo should be able to show off full action choreography without repeated parser errors.
