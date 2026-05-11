# DECISIONS

Key design decisions inherited from the concept and spec documents that govern this implementation:

1. **Ecosystem boundary**: `niri-pypc` is protocol/runtime substrate; `niri-state` is state derivation layer.
2. **Upstream pin**: `niri-ipc = "25.11"` with `json-schema` feature.
3. **Schema export**: Rust binary under `tools/schema_exporter/` using `schemars::schema_for!()`.
4. **IR normalization**: Python script `tools/normalize_ir.py` producing deterministic sorted IR with hashes.
5. **Type generation**: Python script `tools/generate_types.py` producing Pydantic v2 models with discriminated unions.
6. **Unknown variant policy**: Strict outbound; inbound Reply/Event use sentinel fallback via `model_validator`.
7. **Determinism**: No timestamps or non-deterministic values in committed generated artifacts.
8. **Command model**: One-connection-per-request (matches `niri msg` behavior).
9. **Stream model**: Single-consumer with bounded queue (default 256), drop-oldest default, optional fail-fast.
10. **Bundle semantics**: Dual-connection convenience; one side failing does not force-close the other.
11. **Socket discovery**: `NIRI_SOCKET` env var or explicit `NiriConfig.socket_path`; no further fallback.
12. **Error taxonomy**: Base `NiriError` with 8 subclasses; `NiriTimeoutError` dual-inherits `TimeoutError`.
13. **Lifecycle state machine**: Guards invalid transitions with `LifecycleError`; lock-protected for task safety.
14. **Concurrency**: Naturally safe for commands (one conn/request); single-consumer for events; cross-task `close()` allowed.
15. **Reconnection**: Explicit non-goal; callers always create new instances.
