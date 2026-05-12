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
