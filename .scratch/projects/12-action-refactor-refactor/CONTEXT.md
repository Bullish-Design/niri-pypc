# CONTEXT

- Phase 4 complete: failure-path coverage expanded for event stream, bundle lifecycle, and client API boundaries.
- Added event-stream tests for:
  - FAIL_FAST queue pressure (`ProtocolError: Event queue full (FAIL_FAST mode)`).
  - malformed JSON decode surfaced via `next()`.
  - terminal signaling observable even when terminal enqueue path is dropped.
  - `anext(stream)` close semantics.
- Added bundle tests for:
  - partial open failure ensures `client.close()` is invoked.
  - close error ordering preserves first failure when both closers fail.
- Added client test for connect failure mapping:
  - request from non-existent socket surfaces `TransportError` with `operation == "connect"`.
- Validation:
  - `devenv shell -- pytest tests/api/test_event_stream.py tests/api/test_bundle.py tests/api/test_client.py -q` ✅
- Next: Phase 5 type/schema fidelity and generator updates.
