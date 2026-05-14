# CONTEXT

- Phase 2 complete in `NiriEventStream`.
- Implemented:
  - Added terminal signaling primitive (`_terminal_event`) and `_signal_terminal()` helper.
  - Terminal paths now signal terminal state independently of queue enqueue success.
  - Connect lifecycle race hardening: transition to READY before creating reader task.
  - `close()` and `_close_reader_resources()` now tolerate reader/closer races without invalid transitions.
  - Async iterator unified (`__aiter__` returns `self`; `_async_iterator` removed).
- Added tests for:
  - `anext(stream)` after close => `StopAsyncIteration`.
  - terminal signal visibility even if terminal enqueue path is dropped.
  - direct `next()` surfaces decode failures.
  - immediate post-bootstrap close path behavior.
- Validation:
  - `devenv shell -- pytest tests/api/test_event_stream.py -q` ✅
  - `devenv shell -- ruff check src/niri_pypc/api/event_stream.py tests/api/test_event_stream.py` ✅
  - `devenv shell -- ruff format --check src/niri_pypc/api/event_stream.py tests/api/test_event_stream.py` ✅
