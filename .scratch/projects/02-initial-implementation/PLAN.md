# PLAN

NO SUBAGENTS: This project will be executed directly in the main agent only. All file creation, editing, searching, and command execution is done by the primary agent. No delegation.

## Goal

Implement the full `niri-pypc` package end-to-end, following the ordered steps in `NIRI_PYPC_IMPLEMENTATION_GUIDE.md`. This covers the schema pipeline (export → normalize → generate), runtime layer (transport, framing, lifecycle, errors, config), and public API (client, event stream, bundle), with tests, CI gates, and documentation.

## Reference Source

The authoritative execution plan is `.scratch/projects/01-niri-pypc-final-concept/NIRI_PYPC_IMPLEMENTATION_GUIDE.md`. This project file tracks progress against that guide.

## Ordered Steps

| # | Step | Description | Verification |
|---|------|-------------|-------------|
| 0 | Bootstrap and Repository Orientation | Confirm environment, repo structure, working constraints | `uv sync --extra dev` passes |
| 1 | Package Skeleton and Tooling Baseline | Create canonical project layout, base package files, pyproject.toml, devenv.nix | Package imports, pytest suite runs |
| 2 | Upstream Pin Manifest and Schema Directories | Create `schema/upstream-pin.toml` and schema artifact directories | Pin manifest parses correctly |
| 3 | Rust Schema Exporter | Implement `tools/schema_exporter/` to emit JSON Schema for Request/Reply/Event/Action | All 4 schema files exist and are valid JSON |
| 4 | IR Normalization Tool | Implement `tools/normalize_ir.py` to transform schemas into deterministic generator IR | Deterministic output (no diff on re-run) |
| 5 | Type Generator | Implement `tools/generate_types.py` to emit Pydantic models from IR | Deterministic output (no diff on re-run) |
| 6 | Generated Verification Tool | Implement `tools/verify_generated.py` for CI diff-checking | Reports up-to-date and exits 0 |
| 7 | Type Codec Layer | Implement `src/niri_pypc/types/codec.py` (externally-tagged encode/decode) | Roundtrip + unknown variant tests pass |
| 8 | Error Taxonomy | Implement `src/niri_pypc/errors.py` with complete hierarchy | Inheritance and context tests pass |
| 9 | Configuration Layer | Implement `src/niri_pypc/config.py` with defaults and socket resolution | Config tests pass |
| 10 | Framing Module | Implement `src/niri_pypc/transport/framing.py` (newline-delimited JSON) | Framing tests pass |
| 11 | Unix Connection Transport | Implement `src/niri_pypc/transport/connection.py` (`UnixConnection`) | Connection tests pass |
| 12 | Lifecycle Runtime State Machine | Implement `src/niri_pypc/runtime/lifecycle.py` | Lifecycle tests pass |
| 13 | Command Client API (`NiriClient`) | Implement `src/niri_pypc/api/client.py` | Client tests pass |
| 14 | Event Stream API (`NiriEventStream`) | Implement `src/niri_pypc/api/event_stream.py` | Event stream tests pass |
| 15 | Bundle API (`NiriConnectionBundle`) | Implement `src/niri_pypc/api/bundle.py` | Bundle tests pass |
| 16 | Public API Exports and Package Surface | Finalize `__init__.py` re-exports | Public imports resolve |
| 17 | Test Fixtures and Mock Server Infrastructure | Build shared test harness and mock server | Fixtures init/teardown cleanly |
| 18 | Type Tests | Add roundtrip, golden, unknown sentinel, metadata, edge case tests | All type tests pass |
| 19 | Transport and Runtime Tests | Add framing, connection, lifecycle tests | All transport/lifecycle tests pass |
| 20 | API and Integration Tests | Add client, event stream, bundle, and integration tests | All API/integration tests pass |
| 21 | Live Tests (Optional/Gated) | Add real compositor smoke tests gated by `NIRI_SOCKET` | Tests skip cleanly when socket missing |
| 22 | Devenv Scripts and CI Gates | Wire all pipeline scripts and CI quality gates | All commands pass |
| 23 | Documentation and Release Readiness | Update README, contributor docs, changelog | Manual checklist items verified |
| 24 | Final End-to-End Verification Checklist | Run complete pipeline and all quality gates | All green |

## Acceptance Criteria

- Full schema → IR → generated type pipeline is deterministic.
- Runtime/API behavior matches spec contracts.
- Error taxonomy and lifecycle semantics are enforced.
- All required tests pass (types, transport, API, integration).
- Linting, formatting, and type checks pass.
- `verify-generated` passes with no diffs.
- Docs clearly communicate pin/version/boundaries.

NO SUBAGENTS: All work will remain direct and local in the main agent.
