# Context

Completed Step 2 on branch `refactor/protocol-base-layer`:
- `NiriEventStream.connect()` now closes connection and transitions lifecycle to CLOSED if bootstrap fails.
- Reader loop now preserves terminal causes for `ProtocolError` and unexpected exceptions.
- Added regression tests for bootstrap failure and oversized event frame error propagation.

Validation for Step 2:
- `devenv shell -- ruff check src/niri_pypc/api/event_stream.py tests/api/test_event_stream.py` (pass)
- `devenv shell -- ruff format --check src/niri_pypc/api/event_stream.py tests/api/test_event_stream.py` (pass)
- `devenv shell -- pytest -q tests/api/test_event_stream.py` (pass)

Outstanding baseline issue remains:
- `ty check .` currently fails in `src/niri_pypc/types/base.py` and `src/niri_pypc/types/codec.py` (recorded in ISSUES.md).

Next:
- Commit and push Step 2.
- Implement Step 3 (config hardening and lifecycle doc correction).
