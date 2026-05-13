# Context

Completed Step 4 on branch `refactor/protocol-base-layer`:
- Narrowed `NiriEventStream` event types from `BaseModel` to concrete `EventValue` for `next()`, iterator, and queue items.
- Added request-specific overloads to `NiriClient.request()` mapping each request variant to its response variant.

Validation for Step 4:
- `devenv shell -- ruff check src/niri_pypc/api/client.py src/niri_pypc/api/event_stream.py` (pass)
- `devenv shell -- ruff format --check src/niri_pypc/api/client.py src/niri_pypc/api/event_stream.py` (pass)
- `devenv shell -- pytest -q tests/api/test_client.py tests/api/test_event_stream.py` (pass)
- `devenv shell -- ty check .` (still fails with the same pre-existing 7 diagnostics in `src/niri_pypc/types/base.py` and `src/niri_pypc/types/codec.py`)

Next:
- Commit and push Step 4.
- Implement Step 5 (devenv CI script, dead-code cleanup).
