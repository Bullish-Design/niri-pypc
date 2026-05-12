# niri-pypc Test Suite Enhancement Implementation Guide

This guide translates the attached enhancement plan into a concrete implementation path for the exported repository.

## Core direction

Keep the current socket-mock tests as fast contract coverage, add a separate fixture-driven nested `niri` layer for real compositor startup/state checks, and keep host-session tests manual only.

## Recommended order

1. Reclassify existing tests into `contract`, `nested`, and `smoke`.
2. Add fixture directories and scenario manifests.
3. Centralize fake socket helpers.
4. Build a nested niri harness with isolated runtime dir and socket discovery.
5. Add pytest fixtures/markers and failure artifact capture.
6. Implement and stabilize the `minimal` scenario.
7. Add `multi-output` with capability-aware skipping.
8. Add `dense-workspace`, keeping burst/backpressure assertions primarily contract-driven.
9. Wire nested tests into CI and document local commands.

## File-by-file plan

### `pyproject.toml`
Add pytest markers:
- `contract`
- `nested`
- `smoke`
- `niri_scenario(name)`

Also add `PyYAML` to the `dev` extra for scenario loading.

### `tests/helpers/fake_niri_socket.py`
Move the repeated mock server logic here and expose reusable helpers for:
- command-only server
- event-only server
- unified server
- optional transcript capture

Then make `tests/conftest.py` provide fixtures by wrapping these helpers.

### `tests/helpers/nested_niri.py`
Add:
- Pydantic scenario models
- scenario loader/resolver
- nested niri async context manager
- socket discovery/readiness probe
- log/artifact capture
- safety guards against host socket leakage

### `tests/fixtures/niri/configs/`
Create:
- `base-minimal.kdl`
- `multi-output.kdl`
- `dense-workspace.kdl`

Rules:
- no inline generation in Python
- no startup bars or other spawned desktop extras
- deterministic comments at top describing expected state

### `tests/fixtures/niri/scenarios/`
Create YAML manifests that map scenario name to:
- config fixture
- timeouts
- capability flags
- expected counts / names / invariants

### `tests/conftest.py`
Add:
- marker registration
- scenario fixture
- nested harness fixture
- artifact retention hook for failed nested tests

### `tests/integration/test_nested_niri_basic.py`
Start with:
- version request succeeds
- outputs request decodes and matches scenario expectations
- workspaces request decodes and maps to expected outputs
- windows request decodes and stays scoped to nested socket

### `tests/integration/test_nested_niri_events.py`
Add:
- event stream bootstrap
- workspace/output update assertions
- action-driven event tests where feasible
- scenario-specific event expectations

### `tests/live/test_live.py`
Keep for manual host-session verification, but mark as `smoke` and do not rely on it for default CI.

## Key harness decisions

- Launch `niri` with `--config <fixture>`.
- Do **not** use `--session` in nested tests.
- Strip inherited `NIRI_SOCKET` / `NIRI_CONFIG` from the child environment.
- Give the child an isolated `XDG_RUNTIME_DIR` under a temp test dir.
- Discover the created IPC socket inside that runtime dir and verify readiness by issuing a real `VersionRequest()` through `niri-pypc`.
- Always pass the discovered socket explicitly via `NiriConfig(socket_path=...)` in test code.

## Scenario manifest shape

Suggested fields:
- `key`
- `config_fixture`
- `runtime.startup_timeout_s`
- `runtime.ready_probe_interval_s`
- `runtime.settle_delay_s`
- `runtime.event_timeout_s`
- `capabilities.requires_multi_output`
- `expectations.min_outputs`
- `expectations.min_workspaces`
- `expectations.allow_zero_windows`
- `expectations.output_names`
- `expectations.workspace_output_map`

## Practical notes

- `minimal` should assert stable invariants, not fragile exact counts beyond what the fixture guarantees.
- `multi-output` should skip cleanly when the nested backend only exposes one output.
- `dense-workspace` should use nested startup validation plus fake-socket burst fixtures for queue/backpressure assertions.
- Capture log tails, chosen scenario, config path, runtime dir, socket path, and timing summary on failure.

## Done when

- Fixture files are the only source of nested niri startup config.
- Nested tests never touch the host compositor socket.
- `minimal` is reliable locally and in CI.
- `multi-output` is either stable or explicitly capability-gated.
- `dense-workspace` covers large payloads and burst/backpressure behavior deterministically.
- Contract tests stay fast; nested tests are segmented.
