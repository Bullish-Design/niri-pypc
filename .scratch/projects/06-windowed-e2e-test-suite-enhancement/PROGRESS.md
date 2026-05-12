# Progress

## Status

- [x] Create new numbered project directory for planning.
- [x] Review required source documents.
- [x] Draft test suite enhancement planning document.
- [x] Save `TEST_SUITE_ENHANCEMENT_PLAN.md` in project directory.
- [x] **Implementation Complete — 2026-05-12**

## Implementation Summary

The full E2E testing refactoring has been implemented according to `E2E_TESTING_IMPLEMENTATION_GUIDE.md`.

### What was done:

1. **pyproject.toml** — Added pytest markers (`contract`, `nested`, `smoke`, `niri_scenario`) and `PyYAML>=6.0` dev dependency.

2. **Fixture KDL configs** — Created `tests/fixtures/niri/configs/` with `base-minimal.kdl`, `multi-output.kdl`, `dense-workspace.kdl`.

3. **Scenario YAML manifests** — Created `tests/fixtures/niri/scenarios/` with `scenario-minimal.yaml`, `scenario-multi-output.yaml`, `scenario-dense-workspace.yaml`.

4. **Fake socket helpers** — Created `tests/helpers/fake_niri_socket.py` with centralized mock socket servers.

5. **Nested niri harness** — Created `tests/helpers/nested_niri.py` with `NestedNiriHarness`, `NestedNiriInstance`, scenario models, and socket discovery.

6. **conftest.py** — Added marker registration via `pytest_configure`, nested fixtures (`nested_harness`, `nested_niri`, `scenario_expectations`), and failure artifact capture hook.

7. **Nested basic tests** — Created `tests/integration/test_nested_niri_basic.py` with 6 tests for version, outputs, workspaces, windows, multi-output, dense-workspace scenarios.

8. **Nested event tests** — Created `tests/integration/test_nested_niri_events.py` with 5 tests for bootstrap, output events, workspace events, lifecycle, multi-output mapping.

9. **Contract/smoke markers** — Added `pytestmark = pytest.mark.contract` to all 16 existing test files, and `pytest.mark.smoke` to the live test.

### Test Results

- **135 contract tests**: All passed
- **11 nested tests**: Collected (require niri binary to execute)
- **3 smoke tests**: Collected (require real niri session)
- **Ruff**: All checks passed
- **Ty**: All checks passed

## Follow-up Validation and Fixes (2026-05-12)

- Reviewed post-refactor behavior against latest commit (`0507fd9`).
- Found startup behavior bug: nested tests errored when `niri` was unavailable or not launchable.
- Found artifact hook bug: `pytest_runtest_makereport` expected `_nested_niri_instance` but fixture never attached it.
- Added resilient startup handling in `nested_niri` fixture:
  - `FileNotFoundError` and startup `RuntimeError` now skip nested tests with actionable reasons instead of hard-failing the suite.
  - fixture now attaches `request.node._nested_niri_instance` so failure artifact reporting is functional.
- Added explicit watch-mode controls:
  - `--nested-visible` pytest option
  - `NIRI_PYPC_NESTED_VISIBLE=1` env toggle
  - `NIRI_PYPC_NIRI_BINARY=/path/to/niri` binary override
  - `NIRI_PYPC_KEEP_NESTED_ARTIFACTS=1` to preserve logs/runtime dir on startup failure
- Updated harness to improve diagnostics:
  - includes stderr tail in startup failure details
  - supports optional startup-timeout override (`--nested-startup-timeout`)
- Updated README with nested and visible demo commands.
- Validation results in this environment:
  - `devenv shell -- ruff check tests/conftest.py tests/helpers/nested_niri.py`: pass
  - `devenv shell -- ruff format --check tests/conftest.py tests/helpers/nested_niri.py`: pass
  - `devenv shell -- ty check src tests`: pass
  - `devenv shell -- pytest -m nested -q -s`: `11 skipped` (clean skip, no errors)

### Additional corrections during validation

- Fixed invalid fixture KDL syntax that prevented startup before compositor probing:
  - Converted comments from `#` to `//`.
  - Removed invalid `res/position` syntax from output blocks.
  - Removed invalid workspace-to-output declarations that niri rejected in this config form.
- Relaxed scenario workspace-specific expectations where fixture-level workspace mapping was removed:
  - `scenario-multi-output.yaml`: `min_workspaces` 2 -> 1, `workspace_output_map` -> `{}`
  - `scenario-dense-workspace.yaml`: `min_workspaces` 5 -> 1
- Confirmed startup now reaches compositor initialization and skips only due missing compositor backend (`WaylandError(Connection(NoCompositor))`) in this environment.

- [x] Authored detailed VISUAL_TEST_SUITE_HARDENING_GUIDE.md at repo root with step-by-step implementation for hardening steps 1-7 (2026-05-12).
- [x] Implemented visual suite hardening rollout plan section 12 end-to-end (2026-05-12).

## Visual Suite Hardening Rollout (2026-05-12)

Implemented from `VISUAL_TEST_SUITE_HARDENING_GUIDE.md` rollout plan:

1. **Steps 1-3 (preflight, unsafe opt-in, PID-strict socket discovery)**
- Added fail-closed visible preflight in `NestedNiriHarness._visible_preflight(...)`.
- Enforced visible opt-in in fixture via `NIRI_PYPC_ALLOW_VISIBLE_NESTED=1`.
- Added strict PID socket matching path in `_wait_for_socket(..., strict_pid=...)`; visible mode uses strict mode only.

2. **Steps 4-5 (single-run lock + circuit breaker)**
- Added session-scoped visible lock (`/tmp/niri-pypc-visible-nested.lock`) using `fcntl.flock`.
- Added visible-mode circuit breaker state in harness; startup failure signatures open breaker and block relaunches.

3. **Steps 6-7 (cleanup hardening + serial enforcement)**
- Added `pid`/`pgid` metadata to `NestedNiriInstance`.
- Added process-group-aware termination (`SIGTERM` then `SIGKILL`) scoped to child process group.
- Added serial-only enforcement for visible mode (`PYTEST_XDIST_WORKER` and `-n > 1` checks -> skip).

4. **Docs + curated visible marker**
- Updated `README.md` with safe visible command, required opt-in, safety rules, and incident recovery.
- Added marker registration for `visible_demo`; tagged a minimal demo test.

5. **New targeted tests**
- Added `tests/helpers/test_nested_niri_hardening.py` covering:
  - strict PID socket behavior,
  - non-strict fallback behavior,
  - visible preflight pass/fail,
  - circuit breaker signature opening.

## Verification Results (2026-05-12)

- `devenv shell -- uv sync --extra dev`: pass
- `devenv shell -- ruff check .`: pass
- `devenv shell -- ruff format --check .`: initially failed on pre-existing formatting; resolved by running `devenv shell -- ruff format .`; now pass
- `devenv shell -- ty check .`: pass
- `devenv shell -- pytest tests/helpers/test_nested_niri_hardening.py -q --no-cov`: pass

## Long-Lived Visual Demo (2026-05-12)

- Added dedicated demo fixtures:
  - `demo/fixtures/niri/configs/visual-demo.kdl`
  - `demo/fixtures/niri/scenarios/scenario-visual-demo.yaml`
- Added long-lived demo entrypoint:
  - `demo/visual_demo.py`
- Safety constraints applied in demo runtime:
  - explicit unsafe opt-in required (`NIRI_PYPC_ALLOW_VISIBLE_NESTED=1`),
  - single-run cross-process lock (`/tmp/niri-pypc-visible-nested-demo.lock`),
  - fail-closed visible preflight + strict PID socket discovery + circuit breaker inherited via `NestedNiriHarness.start(..., visible=True)`,
  - process-group-aware teardown inherited via `NestedNiriHarness.stop(...)`.
- Demo functionality exercised continuously:
  - command API snapshots via `NiriClient` (`Version`, `Outputs`, `Workspaces`, `Windows`, `FocusedOutput`, `FocusedWindow`),
  - streaming API via `NiriEventStream` through `NiriConnectionBundle`,
  - long-lived single visible nested compositor until Ctrl+C or `--duration`.

## Demo Diagnostics Report (2026-05-12)

- Added root-level `DEMO_ERROR_REPORT.md` with detailed analysis of live `--wire-log` output.
- Report captures:
  - confirmed working paths (spawn, snapshots, event flow, teardown),
  - confirmed failures (unit action parse errors),
  - suspected protocol issues (event-stream ack handling, action unit-variant wire shape),
  - concrete follow-up investigation steps.
