# E2E Testing Ideas for `niri-pypc`

## Table of contents

1. Scope and goals
2. Constraints and assumptions
3. Test pyramid for niri IPC integrations
4. Tier 1: socket-level contract tests (fast, CI default)
5. Tier 2: nested-session integration tests (opt-in CI / local)
6. Tier 3: real-session smoke tests (manual pre-release)
7. Fixture and scenario catalog
8. Failure injection and resilience checks
9. Test harness architecture (Python)
10. CI pipeline design and gating
11. Observability and diagnostics
12. Risks, unknowns, and rollout plan

## 1. Scope and goals

`niri-pypc` is an IPC transport/client library. E2E confidence should prove:

- command requests serialize correctly, reach a real niri socket, and decode replies correctly;
- event streaming behavior is correct under startup, burst, malformed payload, disconnect, and timeout conditions;
- environment isolation prevents tests from attaching to the developer's live niri session by accident;
- parser behavior stays forward-compatible with additive upstream changes.

## 2. Constraints and assumptions

- niri development workflow emphasizes nested-window testing and local builds; this maps well to library integration tests where we should avoid hijacking host sessions.
- library CI must remain fast and deterministic for default runs; heavy nested compositor tests should be opt-in or scheduled.
- IPC JSON is the stable contract boundary; human-readable command output is not a stable parse target.
- `NIRI_SOCKET` is the critical endpoint selector. Test harnesses must explicitly set/unset it.

## 3. Test pyramid for niri IPC integrations

Use a three-tier model:

1. Tier 1 (default CI): socket-level contract tests with fake UNIX servers.
2. Tier 2 (opt-in CI + local pre-merge): nested niri session integration.
3. Tier 3 (manual release gate): smoke tests against a real user session.

This gives fast feedback on every PR, meaningful protocol confidence before merge, and final sanity before release.

## 4. Tier 1: socket-level contract tests (fast, CI default)

Purpose: validate protocol wiring without running niri.

Implementation ideas:

- Keep existing mock socket fixtures as the baseline.
- Add replay fixtures for representative `Reply` and `Event` payloads.
- Add fixture classes for error paths:
  - abrupt EOF,
  - malformed JSON,
  - oversized frames,
  - delayed frame to trigger timeout,
  - split writes to simulate partial frame arrival.

Key assertions:

- request encoder shape (`"Version"`, tagged payloads, etc.);
- frame boundary handling and newline requirements;
- `max_frame_size` behavior over and under threshold;
- event queue/backpressure semantics (`DROP_OLDEST`, `FAIL_FAST`);
- error taxonomy correctness (`TransportError`, `ProtocolError`, `DecodeError`, `NiriTimeoutError`).

## 5. Tier 2: nested-session integration tests (opt-in CI / local)

Purpose: validate real compositor IPC behavior in isolation.

Approach:

- Launch nested niri instance from a dedicated test script.
- Use dedicated config file and isolated runtime directory.
- Export test-specific `NIRI_SOCKET` for the test process only.
- Run a focused integration test subset against that socket.
- Tear down nested compositor and assert clean exit.

Isolation requirements:

- hard-fail if `NIRI_SOCKET` points to an existing non-test path;
- record PID and socket path of nested instance;
- avoid inherited systemd/dbus environment leakage by overriding env explicitly in test runner.

Candidate scenarios:

- `VersionRequest`, `OutputsRequest`, `WorkspacesRequest`, `WindowsRequest` round-trips;
- event stream initial snapshot + update handling;
- reconnect behavior after nested compositor exit/restart (if/when reconnect support exists);
- large payload request for high-window-count simulations.

## 6. Tier 3: real-session smoke tests (manual pre-release)

Purpose: verify no regressions in realistic user environments.

Manual checklist:

- run a curated script against active session (`NIRI_SOCKET` discovered naturally);
- verify command round-trips and event stream startup;
- run a short burst test while changing workspaces/windows;
- confirm clean shutdown and no hanging tasks.

Keep this tier short and non-destructive. It should not be part of default CI.

## 7. Fixture and scenario catalog

Proposed fixture files under `tests/fixtures/ipc/`:

- `reply_ok_version.json`
- `reply_ok_outputs_large.json`
- `reply_err_generic.json`
- `event_initial_state_sequence.jsonl`
- `event_workspace_updates.jsonl`
- `event_unknown_variant.json`
- `event_malformed_frame.raw`

Scenario matrix (minimum):

1. small request/small reply
2. small request/large reply
3. unknown variant reply/event
4. malformed JSON frame
5. oversized frame
6. socket closes mid-stream
7. event burst over queue capacity

## 8. Failure injection and resilience checks

Add explicit failure injection hooks in test servers:

- close on connect;
- close after N frames;
- stall before delimiter;
- send delimiter-free blob;
- send invalid UTF-8 bytes;
- send duplicate/new additive keys.

These checks prevent regressions where parser strictness or framing assumptions accidentally narrow compatibility.

## 9. Test harness architecture (Python)

Recommended components:

- `tests/helpers/fake_niri_socket.py`:
  - async UNIX server class,
  - scripted response/event playback,
  - deterministic timing controls.
- `tests/helpers/nested_niri.py`:
  - process launcher for nested niri,
  - temporary config + env setup,
  - lifecycle/cleanup guards.
- pytest markers:
  - `@pytest.mark.contract` (Tier 1)
  - `@pytest.mark.nested` (Tier 2)
  - `@pytest.mark.smoke` (Tier 3/manual)

Command examples:

```bash
devenv shell -- pytest -m contract -q
devenv shell -- pytest -m nested -q
```

## 10. CI pipeline design and gating

Suggested pipeline:

1. PR default:
   - lint/format/typecheck,
   - Tier 1 contract tests.
2. PR optional label or nightly:
   - Tier 2 nested tests.
3. Release workflow:
   - Tier 1 + Tier 2 required,
   - manual Tier 3 checklist sign-off.

Artifacts to retain on failures:

- nested compositor logs,
- test harness env summary (redacted),
- serialized frames sent/received around failure.

## 11. Observability and diagnostics

For flaky/failing IPC tests, capture:

- timestamped frame transcript (hex + UTF-8 fallback),
- socket path and process metadata,
- timeout budget and elapsed duration per operation,
- event queue depth snapshots during burst tests.

Add debug mode env var (e.g., `NIRI_PYPC_TEST_TRACE=1`) to enable verbose harness logs without polluting normal runs.

## 12. Risks, unknowns, and rollout plan

Risks:

- nested compositor availability in CI runners;
- test flakiness due to timing and compositor startup variability;
- accidental coupling to host desktop state.

Unknowns to resolve early:

- best launcher command for nested niri in headless/semi-headless CI;
- minimal stable config for integration tests;
- acceptable runtime budget for Tier 2.

Rollout plan:

1. Strengthen Tier 1 first (immediate).
2. Add local-only Tier 2 harness and docs.
3. Promote Tier 2 to opt-in CI.
4. Stabilize and gate releases on Tier 2 + Tier 3 checklist.
