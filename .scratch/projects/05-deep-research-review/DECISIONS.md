# DECISIONS

## 2026-05-12: Fix stream limit at connection creation

- Decision: pass an explicit `stream_limit` into `asyncio.open_unix_connection()` based on configured `max_frame_size`.
- Why: `StreamReader.readuntil()` is bounded by the stream limit before application-level `max_frame_size` checks; without this, large frames fail prematurely.
- Outcome: `NiriClient` and `NiriEventStream` now pass `max(max_frame_size + 1, DEFAULT_STREAM_LIMIT)`.

## 2026-05-12: Convert `LimitOverrunError` to protocol failure

- Decision: catch `asyncio.LimitOverrunError` in `read_frame()` and raise `ProtocolError`.
- Why: consumers should see deterministic protocol semantics for oversize frames rather than low-level asyncio errors.

## 2026-05-12: E2E strategy as three-tier test pyramid

- Decision: document Tier 1 contract tests, Tier 2 nested-session integration, Tier 3 manual real-session smoke.
- Why: balances CI speed, environment isolation, and confidence against real compositor behavior.
