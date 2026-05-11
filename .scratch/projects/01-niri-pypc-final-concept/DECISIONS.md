# DECISIONS

1. Final concept document location:
   `.scratch/projects/01-niri-pypc-final-concept/NIRI_PYPC_CONCEPT_FINAL.md`
2. Ecosystem boundary:
   `niri-pypc` is protocol/runtime substrate; `niri-state` is state derivation layer.
3. Unknown variant policy:
   strict outbound requests/actions; inbound responses/events use explicit unknown sentinels.
4. Determinism policy:
   no non-deterministic timestamps in committed generated artifacts.
5. Dual-channel convenience naming:
   prefer `NiriConnectionBundle` to avoid `NiriSession` state-store implications.
6. Mismatch policy:
   default fail-fast strict mode with optional relaxed continuation mode.
7. Event stream policy:
   bounded queue with fail-fast overflow by default; no silent event dropping.
8. Concurrency policy:
   concurrent requests supported; `close()` cross-task allowed; single-consumer stream contract.
