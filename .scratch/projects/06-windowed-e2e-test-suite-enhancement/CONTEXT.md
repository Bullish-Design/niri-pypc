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
