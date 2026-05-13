# Context

Completed Step 3 on branch `refactor/protocol-base-layer`:
- Converted `NiriConfig` from dataclass to frozen Pydantic model with positive numeric constraints.
- Added config tests for string->Path coercion and invalid non-positive values.
- Updated lifecycle manager docstring to correctly describe asyncio task safety (not thread safety).

Validation for Step 3:
- `devenv shell -- ruff check src/niri_pypc/config.py src/niri_pypc/runtime/lifecycle.py tests/api/test_config.py` (pass)
- `devenv shell -- ruff format --check src/niri_pypc/config.py src/niri_pypc/runtime/lifecycle.py tests/api/test_config.py` (pass)
- `devenv shell -- pytest -q tests/api/test_config.py tests/api/test_lifecycle.py` (pass)
- `devenv shell -- ty check .` (still fails with pre-existing diagnostics in `src/niri_pypc/types/base.py` and `src/niri_pypc/types/codec.py`)

Next:
- Commit and push Step 3.
- Implement Step 4 (public typing improvements).
