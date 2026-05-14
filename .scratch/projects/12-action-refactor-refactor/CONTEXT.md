# CONTEXT

- Phase 1 complete: transport framing invariant + read-timeout poisoning.
- Implemented:
  - `UnixConnection.write_frame` now appends a newline only when missing.
  - `NiriClient.request` and `NiriEventStream._bootstrap` no longer manually append newlines.
  - `UnixConnection.read_frame` now sets `_closed = True` on timeout before raising `NiriTimeoutError`.
- Added regression tests for:
  - newline append idempotency in transport writes.
  - client/event stream requests remain single-newline terminated.
  - read-timeout poisons connection and blocks subsequent read/write.
- Validation run:
  - targeted tests `tests/transport/test_connection.py tests/api/test_client.py tests/api/test_event_stream.py` passed.
  - repo-wide `ruff check .` and `ruff format --check .` still fail only on pre-existing import-order issues in `src/niri_pypc/actions.py` and `tests/test_actions.py`.
- Next: Phase 2 event stream robustness/lifecycle refactor.
