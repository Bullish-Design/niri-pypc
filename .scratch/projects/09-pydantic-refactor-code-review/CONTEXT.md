# Context

Completed Step 1 on branch `refactor/protocol-base-layer`:
- runtime `__version__` now resolves from installed distribution metadata
- removed stale `_version.py`
- added package metadata classifiers/urls and `py.typed` packaging
- added `tests/test_package_metadata.py`

Validation run:
- `devenv shell -- uv sync --extra dev` (done)
- `devenv shell -- ruff check .` (pass)
- `devenv shell -- ruff format --check .` (pass)
- `devenv shell -- pytest -q tests/test_package_metadata.py` (pass)
- `devenv shell -- ty check .` (fails with pre-existing diagnostics in `src/niri_pypc/types/base.py` and `src/niri_pypc/types/codec.py`)

Next:
- Commit and push Step 1.
- Implement Step 2 (event stream hardening).
