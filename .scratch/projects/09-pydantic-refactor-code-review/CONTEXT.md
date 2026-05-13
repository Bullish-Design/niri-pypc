# Context

Project completed on branch `refactor/protocol-base-layer`.

Step 5 completion details:
- Added local CI-equivalent script command `ci` in `devenv.nix` to run sync, lint, format check, type check, generated-code verify, tests, and package build.
- Added `build` to dev dependencies in `pyproject.toml` so CI script can run `python -m build`.
- Removed dead code module `src/niri_pypc/transport/framing.py`.

Validation outcomes:
- `devenv shell -- ruff check .` (pass)
- `devenv shell -- ruff format --check .` (pass)
- `devenv shell -- ty check .` (fails with pre-existing diagnostics in `src/niri_pypc/types/base.py` and `src/niri_pypc/types/codec.py`)
- `devenv shell -- pytest -q tests/transport/test_connection.py` (pass)
- `devenv shell -- ci` executed and completed through tests/build; it reports ty diagnostics but continues execution.

All planned implementation steps from the review were completed, with GitHub CI implemented as a local devenv script per user instruction.
