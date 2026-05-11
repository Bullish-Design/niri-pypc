# DECISIONS

1. Final concept document location:
   `.scratch/projects/01-niri-pypc-final-concept/NIRI_PYPC_CONCEPT_FINAL.md`
2. Ecosystem boundary:
   `niri-pypc` is protocol/runtime substrate; `niri-state` is state derivation layer.
3. Upstream pin version:
   `niri-ipc = "25.11"` — explicit, recorded in `schema/upstream-pin.toml` and exporter `Cargo.toml`.
4. Schema export mechanism:
   Use `niri-ipc`'s `json-schema` cargo feature with `schemars::schema_for!()` in a small Rust binary under `tools/schema_exporter/`. Devenv script invokes it.
5. IR normalization:
   Separate Python script (`tools/normalize_ir.py`) transforms raw JSON Schema into a stable, generator-ready IR with explicit versioning and schema hashes.
6. Pydantic strategy:
   Maximize native Pydantic v2 features (discriminated unions, model validators, field aliases, model serializers). Use `model_validator(mode="before")` for externally-tagged enum dispatch.
7. Unknown variant policy:
   Strict outbound requests/actions; inbound responses/events use explicit unknown sentinels via model_validator fallback.
8. Determinism policy:
   No non-deterministic timestamps in committed generated artifacts.
9. Dual-channel convenience naming:
   Prefer `NiriConnectionBundle` to avoid `NiriSession` state-store implications.
10. Bundle lifetime semantics:
    Command and event connections are independent within the bundle. One failing does not force-close the other.
11. Mismatch policy:
    Post-connect `Version` request check (not a handshake). Default fail-fast strict mode with optional relaxed continuation mode.
12. Event stream backpressure:
    Bounded queue (default 256). Default: drop-oldest with warning log. Optional strict mode: fail-fast with backpressure error.
13. Concurrency policy:
    One-connection-per-request makes command concurrency naturally safe. Single-consumer stream contract. Cross-task `close()` allowed.
14. Reconnection policy:
    Explicit non-goal. Callers create new instances. Downstream libraries may add reconnection.
15. Socket discovery:
    `NIRI_SOCKET` env var or explicit config argument. No further fallback.
16. Python version:
    3.13+ (matches `pyproject.toml` and `devenv.nix`).
17. Error taxonomy:
    Base `NiriError` with 8 specific subclasses. `NiriTimeoutError` dual-inherits from `NiriError` and `TimeoutError`.
18. Command connection model:
    One-connection-per-request to match upstream `niri msg` behavior. May revisit if pooling is beneficial.
