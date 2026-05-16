# Context

Completed requested test expansions from `FINAL_CODE_REVIEW.md`:

- `TEST-1` full variant roundtrip suite:
  - Replaced limited `tests/types/test_roundtrip.py` coverage with comprehensive parametrized cases for all request variants, all known event variants, and all reply/response variants.
  - Added canonical expected-shape handling for unit/newtype encodings and optional-field normalization in serialized window/window-layout payloads.

- `TEST-2` concurrent event stream tests:
  - Added `TestEventStreamConcurrency` in `tests/api/test_event_stream.py` covering:
    - simultaneous `next()` waiters consuming distinct events,
    - `close()` unblocking a pending `next()`,
    - reader decode failure unblocking a pending `next()` with `DecodeError`,
    - rapid connect/close cycles.

Validation run for this task:
- `devenv shell -- uv sync --extra dev`
- `devenv shell -- ruff check .`
- `devenv shell -- ruff format --check .`
- `NIRI_PYPC_NESTED_VISIBLE=0 devenv shell -- pytest -m "not nested and not visible_demo and not smoke" tests/types/test_roundtrip.py tests/api/test_event_stream.py`
- Result: `67 passed`.
