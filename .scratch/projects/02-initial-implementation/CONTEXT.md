# CONTEXT

## What's Done

Full `niri-pypc` library implementation is complete. All 25 steps from `NIRI_PYPC_IMPLEMENTATION_GUIDE.md` have been executed.

### Schema Pipeline (Steps 0-6)
- Rust schema exporter (`tools/schema_exporter/`) exports `Request`, `Reply`, `Event`, `Action` schemas
- IR normalization tool (`tools/normalize_ir.py`) produces deterministic IR with hashes
- Type generator (`tools/generate_types.py`) produces Pydantic v2 models with externally-tagged enums
- Verification tool (`tools/verify_generated.py`) ensures generated code is up-to-date

### Core Manual Code (Steps 7-16)
- **`types/codec.py`**: Externally-tagged enum encode/decode primitives
- **`types/generated/`**: Auto-generated protocol type models
- **`errors.py`**: Complete `NiriError` exception hierarchy (8 subclasses)
- **`config.py`**: `NiriConfig` frozen dataclass with socket discovery
- **`transport/framing.py`**: Newline-delimited JSON frame encode/decode
- **`transport/connection.py`**: `UnixConnection` with timeout/oversize/EOF handling
- **`runtime/lifecycle.py`**: State machine with valid transition guardrails
- **`api/client.py`**: `NiriClient` with one-connection-per-request
- **`api/event_stream.py`**: `NiriEventStream` with background reader and backpressure
- **`api/bundle.py`**: `NiriConnectionBundle` with error isolation
- **`__init__.py`**: Public API re-exports

### Tests (Steps 17-21)
- 88 tests total (excluding optional live tests)
- Config, lifecycle, framing, connection, client, event stream, bundle tests
- Type roundtrip, unknown variant sentinel, metadata, edge case tests
- Integration tests for command/event/bundle flows
- Live tests gated by `NIRI_SOCKET`

### Final Verification (Step 24)
- Pipeline: export -> normalize -> generate -> verify: OK
- pytest: 88/88 pass
- ruff check: Only generated-file issues remain (I001, E501 in auto-generated union types)
- ruff format --check: All files formatted
- ty check src/niri_pypc/: All checks passed
- verify-generated: Up to date

## Upstream Pin
- `niri-ipc 25.11` with `json-schema` feature
