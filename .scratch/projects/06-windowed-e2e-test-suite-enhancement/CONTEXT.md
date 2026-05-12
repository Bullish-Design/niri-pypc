# Context

## Current State

Created project `06-windowed-e2e-test-suite-enhancement` to deliver a planning artifact for improving windowed E2E testing.

Inputs reviewed:
- `.scratch/projects/05-deep-research-review/E2E_TESTING_IDEAS.md`
- `.scratch/projects/05-deep-research-review/niri-docs-developing-overview.md`

## Completed This Session

- Established project-scoped tracking files.
- Captured assumptions and decisions for fixture-based niri config approach.
- Authored `TEST_SUITE_ENHANCEMENT_PLAN.md` covering architecture, fixture layout, scenario matrix, CI gating, and rollout.

## Next Likely Step

Implement the plan by creating fixture directories, harness helpers, and first nested/windowed integration tests in the main test suite.

## 2026-05-12 Follow-up Context

- User requested verification of the newly refactored nested/windowed suite and a visible demo mode.
- Verified latest commit (`0507fd9`) and executed nested tests locally.
- Initial behavior was not acceptable for non-niri environments: nested tests hard errored due startup timeout.
- Applied fixes to:
  - degrade launch failures to skips (so suite behavior is predictable on machines without runnable nested niri),
  - wire failure-artifact capture correctly by attaching the nested instance to the test item,
  - add explicit visible watch mode and startup configurability for demos.
- Current state:
  - nested tests no longer fail hard in unsupported environments (`11 skipped`),
  - watch mode is available via `--nested-visible` / `NIRI_PYPC_NESTED_VISIBLE=1`,
  - README documents exact commands and toggles.

- Added repo-root VISUAL_TEST_SUITE_HARDENING_GUIDE.md with concrete implementation sequence, code-touch guidance, verification plan, and rollout notes for visible nested test hardening.

## 2026-05-12 Visual Hardening Rollout Applied

- Implemented all rollout-plan changes from section `12) Rollout Plan` in `VISUAL_TEST_SUITE_HARDENING_GUIDE.md`.
- Core hardening landed in:
  - `tests/helpers/nested_niri.py`
  - `tests/conftest.py`
  - `tests/integration/test_nested_niri_basic.py`
  - `README.md`
  - `tests/helpers/test_nested_niri_hardening.py` (new)
- Notable behavior now:
  - visible mode requires explicit `NIRI_PYPC_ALLOW_VISIBLE_NESTED=1`,
  - visible mode validates parent Wayland socket preflight before spawn,
  - visible mode uses strict PID socket matching only,
  - visible mode is protected by a cross-process lock and serial-only rules,
  - startup compositor/backend failures open a session circuit breaker,
  - cleanup is process-group-aware (child pgid only).
- Validation status:
  - `uv sync`, `ruff check .`, `ruff format --check .`, `ty check .` all passing.
  - Added targeted unit tests for hardening logic; they pass with `--no-cov`.

## 2026-05-12 Long-Lived Demo Addition

- User requested a long-lived visual demo independent from per-test nested lifecycle.
- Implemented `demo/visual_demo.py` with dedicated demo fixtures in `demo/fixtures/...`.
- Demo keeps a single visible nested niri instance alive and continuously exercises:
  - command snapshots (version, outputs, workspaces, windows, focused output/window),
  - event stream ingestion and event-type counters,
  - bundle lifecycle management.
- Safety constraints preserved:
  - requires explicit `NIRI_PYPC_ALLOW_VISIBLE_NESTED=1`,
  - enforces single-run lock across processes,
  - reuses hardened visible harness behavior for fail-closed preflight, strict PID socket matching, circuit breaker, and process-group cleanup.

## 2026-05-12 Wire-Log Analysis Artifact

- User provided full `demo/visual_demo.py --wire-log` output for diagnosis.
- Added `DEMO_ERROR_REPORT.md` at repository root summarizing observed runtime behavior and protocol findings:
  - event-stream ack appears to surface as `UnknownEvent` (`Ok`/`Handled`) during startup,
  - many unit action payloads (string form) are rejected with compositor parse errors,
  - structured action payloads with arguments succeed,
  - command snapshots/event stream/spawn/teardown remain operational.
