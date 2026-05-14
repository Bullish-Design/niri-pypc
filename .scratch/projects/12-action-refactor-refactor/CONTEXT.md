# CONTEXT

- Phase 0 complete on branch `refactor/action-review-guide-implementation`.
- Baseline commands run:
  - `devenv shell -- uv sync --extra dev` ✅
  - `devenv shell -- ruff check .` ❌ pre-existing import-order issues in:
    - `src/niri_pypc/actions.py`
    - `tests/test_actions.py`
  - `devenv shell -- ruff format --check .` ❌ would reformat same two files
  - `NIRI_PYPC_NESTED_VISIBLE=0 devenv shell -- pytest -m "not nested and not visible_demo and not smoke"` ✅
- Note: `ruff` runs also emitted `E902` path artifact (`.--check`) due to command execution context, but core actionable baseline failures are the two import-order files above.
- Next: Phase 1 transport framing and timeout hardening.
