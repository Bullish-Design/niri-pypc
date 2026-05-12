# Test Suite Enhancement Plan: Windowed E2E with Fixture-Based Niri Config

## 1. Goal

Enhance `niri-pypc` end-to-end testing with a reliable windowed (nested) niri integration layer where startup configuration is always sourced from fixture files inside the test tree.

This ensures developers can:
- inspect and verify exact starting compositor state,
- swap between multiple known configurations,
- run realistic integration scenarios without attaching to their live session.

## 2. Scope

In scope:
- Add a fixture-driven config mechanism for nested/windowed niri runs.
- Define a scenario matrix that can select different niri config fixtures.
- Add harness conventions for launching nested niri with explicit `NIRI_SOCKET` isolation.
- Define CI and local execution strategy for these tests.

Out of scope (for this phase):
- Full implementation of all scenarios.
- Real-session destructive automation.

## 3. Guiding Constraints

- Preserve fast default CI by keeping heavyweight integration tests opt-in/segmented.
- Treat IPC JSON framing/contracts as the stable boundary.
- Prevent accidental use of host session socket by default.
- Keep all environment-dependent commands runnable with `devenv shell -- ...`.

## 4. Proposed Test Layout

```text
tests/
  fixtures/
    ipc/
      ...existing and new socket payload fixtures...
    niri/
      configs/
        base-minimal.kdl
        multi-output.kdl
        dense-workspace.kdl
      scenarios/
        scenario-minimal.yaml
        scenario-multi-output.yaml
        scenario-dense-workspace.yaml
  helpers/
    nested_niri.py
    fake_niri_socket.py
  integration/
    test_nested_niri_basic.py
    test_nested_niri_events.py
```

Notes:
- `tests/fixtures/niri/configs/*.kdl` are the authoritative startup config fixtures.
- `tests/fixtures/niri/scenarios/*.yaml` map test intents to config fixture names and runtime options.

## 5. Fixture-Based Niri Config Strategy

### 5.1 Core Principle

Never inline niri config in Python test code for windowed E2E. Always point nested niri startup to a checked-in fixture file under `tests/fixtures/niri/configs/`.

### 5.2 Scenario Selection

Each nested E2E test picks a scenario key (or explicit fixture name), and the harness resolves:
- config path,
- expected capabilities/assumptions,
- optional startup tuning (timeouts, retry windows).

### 5.3 Swap-Friendly Mechanism

Support two mechanisms:
- per-test marker/parametrization selecting scenario fixture,
- optional env override for local debugging (for example `NIRI_PYPC_TEST_SCENARIO=multi-output`).

Validation guardrails:
- fail fast if requested scenario/config fixture does not exist,
- log chosen fixture path at test startup,
- include fixture identity in failure output.

## 6. Harness Design (Windowed/Nested)

`tests/helpers/nested_niri.py` should provide:
- context manager to start/stop nested niri,
- explicit temp runtime dir,
- generated socket path within temp dir,
- strict `NIRI_SOCKET` export only for child/test process scope,
- startup readiness probe with bounded timeout,
- log capture for failure artifacts.

Safety checks:
- reject socket paths outside allowed temp test dirs,
- reject inherited host socket usage when running marked nested tests.

## 7. Scenario Matrix (Initial)

1. `minimal` using `base-minimal.kdl`
- Verify `Version`, `Outputs`, `Workspaces`, `Windows` request/reply round-trips.

2. `multi-output` using `multi-output.kdl`
- Verify output/workspace mapping behavior and event stream updates.

3. `dense-workspace` using `dense-workspace.kdl`
- Verify larger payload handling and queue behavior under event bursts.

Each scenario should pair with relevant IPC fixtures where needed for deterministic assertions.

## 8. Test Markers and Command Conventions

Markers:
- `@pytest.mark.contract` for socket-only tests,
- `@pytest.mark.nested` for windowed integration,
- `@pytest.mark.smoke` for manual real-session checks.

Planned commands:

```bash
devenv shell -- pytest -m contract -q
devenv shell -- pytest -m nested -q
devenv shell -- pytest -m "nested and not slow" -q
```

## 9. CI and Gating Plan

- PR default: lint/format/typecheck + `contract` tests.
- Opt-in/nightly: `nested` tests with fixture-based configs.
- Release gate: require passing `contract` and `nested`, plus manual smoke checklist.

Failure artifact retention for nested jobs:
- selected config fixture name/path,
- nested niri logs,
- frame transcript snippets around failure,
- timing summary (startup/operation timeout values).

## 10. Rollout Phases

1. Scaffold fixture directories and baseline config fixtures.
2. Add nested harness with strict isolation checks.
3. Implement `minimal` scenario tests and stabilize.
4. Add `multi-output` and `dense-workspace` scenarios.
5. Add CI opt-in nested job and document local workflow.
6. Promote nested job to stronger gating once stable.

## 11. Risks and Mitigations

- Startup flakiness in nested mode:
  - Mitigate with explicit readiness probe, retry budget, and structured logs.

- Config drift between fixtures and test expectations:
  - Mitigate with scenario metadata and explicit assertions tied to fixture identity.

- Accidental host-session interaction:
  - Mitigate with strict socket path checks and env sanitization in harness.

## 12. Definition of Done (Planning Phase)

This planning phase is complete when:
- fixture-first config strategy is documented,
- scenario-based swapping approach is documented,
- test layout/harness/CI rollout are concretely defined for implementation.
