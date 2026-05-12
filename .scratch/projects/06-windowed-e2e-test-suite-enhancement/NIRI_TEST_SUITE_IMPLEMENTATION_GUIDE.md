Here’s the implementation guide, tuned to the exported repo and the attached plan. The short version is: keep the current mock-socket tests as fast `contract` coverage, add a new fixture-driven `nested` layer for real compositor startup/state checks, and demote host-session tests to manual `smoke` coverage. That matches both the current spec’s layered test structure and the enhancement plan’s fixture-first nested goal.  

A copy is here: [niri_test_suite_enhancement_implementation_guide.md](sandbox:/mnt/data/niri_test_suite_enhancement_implementation_guide.md)

## 1. Target end state

You should end up with three clearly separated test bands:

1. **Contract tests**
   Everything that talks to fake Unix sockets only. This includes the current transport tests, most API tests, and the current “integration” tests that are really socket-contract tests.

2. **Nested tests**
   Real `niri` launched as a nested/windowed compositor, always from checked-in KDL fixtures and always with an isolated runtime dir and isolated IPC socket.

3. **Smoke tests**
   Manual host-session checks against a real user compositor, only when explicitly requested.

That division fits the plan’s goal of preserving fast default CI while adding a realistic nested layer.  

## 2. First structural decision: do not replace the current mock layer

Do **not** rewrite the current socket-backed tests into nested tests. The current suite already has value as fast IPC-contract coverage, and the spec explicitly treats mock-socket and live testing as separate layers. 

So the migration should be:

* current `transport/`, `api/`, and current socket-backed `integration/` tests → mark as `contract`
* new nested compositor tests → add under `tests/integration/` with `@pytest.mark.nested`
* current `tests/live/test_live.py` → keep, but mark as `smoke`

That gives you a clean pyramid instead of one blurry integration bucket.

## 3. Add the missing fixture/scenario tree first

Create exactly this tree from the plan:

```text
tests/
  fixtures/
    ipc/
    niri/
      configs/
        base-minimal.kdl
        multi-output.kdl
        dense-workspace.kdl
      scenarios/
        scenario-minimal.yaml
        scenario-multi-output.yaml
        scenario-dense-workspace.yaml
  helpers/
    nested_niri.py
    fake_niri_socket.py
  integration/
    test_nested_niri_basic.py
    test_nested_niri_events.py
```

This is the backbone of the whole feature. The plan is explicit that checked-in KDL files are the authoritative startup source, and scenario YAML maps test intent to config/runtime expectations. 

## 4. Reclassify the existing tests before adding new ones

Do this early so the suite stays understandable while you build the nested layer.

### `pyproject.toml`

Add pytest markers:

```toml
[tool.pytest.ini_options]
addopts = "-q --cov=niri_pypc --cov-report=term-missing"
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
  "contract: socket-only IPC contract tests",
  "nested: nested/windowed niri integration tests",
  "smoke: manual real-session checks",
  "niri_scenario(name): select nested niri scenario fixture",
]
```

### Apply markers

* mark current socket-backed tests as `contract`
* mark `tests/live/test_live.py` as `smoke`
* mark new real nested tests as `nested`

I would also rename mentally, even if not on disk yet:

* current `tests/integration/test_command_flow.py` → contract-style
* current `tests/integration/test_event_flow.py` → contract-style
* current `tests/integration/test_independence.py` → contract-style

That aligns the suite with the plan’s command conventions. 

## 5. Centralize the fake socket helpers next

Right now the export duplicates mock server logic across root conftest and API test files. Move that into `tests/helpers/fake_niri_socket.py` first.

Create one reusable helper with modes for:

* command reply server
* event stream server
* unified command + event server
* optional frame transcript capture

Then make `tests/conftest.py` expose fixtures by wrapping that helper.

This cleanup matters because the plan already reserves `tests/helpers/fake_niri_socket.py`, and it keeps the new nested harness from being mixed with old fixture duplication. 

## 6. Build the scenario loader with Pydantic models

Use Pydantic for the scenario manifests. A good shape is:

```python
from pathlib import Path
from pydantic import BaseModel, Field

class ScenarioRuntime(BaseModel):
    startup_timeout_s: float = 15.0
    ready_probe_interval_s: float = 0.1
    settle_delay_s: float = 0.25
    event_timeout_s: float = 3.0

class ScenarioCapabilities(BaseModel):
    requires_multi_output: bool = False

class ScenarioExpectations(BaseModel):
    min_outputs: int = 1
    min_workspaces: int = 1
    allow_zero_windows: bool = True
    output_names: list[str] = Field(default_factory=list)
    workspace_output_map: dict[str, str] = Field(default_factory=dict)

class NestedNiriScenario(BaseModel):
    key: str
    config_fixture: str
    runtime: ScenarioRuntime = Field(default_factory=ScenarioRuntime)
    capabilities: ScenarioCapabilities = Field(default_factory=ScenarioCapabilities)
    expectations: ScenarioExpectations = Field(default_factory=ScenarioExpectations)
```

Then implement loader logic in `tests/helpers/nested_niri.py`:

* load YAML
* validate with `NestedNiriScenario`
* resolve `config_fixture` to `tests/fixtures/niri/configs/...`
* fail fast if the YAML or KDL file is missing
* apply optional env override via `NIRI_PYPC_TEST_SCENARIO`

That matches the plan’s per-test selection plus env override requirement. 

## 7. Important correction: isolate via `XDG_RUNTIME_DIR`, not a guessed socket flag

The plan says the harness should produce a generated socket path inside a temp dir. Implement that by giving nested `niri` its own temporary `XDG_RUNTIME_DIR`, then discovering the socket it creates there.

Do **not** assume a dedicated CLI flag exists for choosing the IPC socket path. The current IPC docs describe connecting through `$NIRI_SOCKET`; they do not document a separate user-facing IPC-socket-path flag. That means the safest implementation is isolated runtime dir + socket discovery. This is an inference from the current docs. ([GitHub][1])

## 8. Launch nested `niri` the safe way

In `tests/helpers/nested_niri.py`, the async context manager should:

1. Create a temp root with:

   * `runtime/`
   * `logs/`
   * `artifacts/`

2. Sanitize the child environment:

   * remove inherited `NIRI_SOCKET`
   * remove inherited `NIRI_CONFIG`
   * set `XDG_RUNTIME_DIR` to the temp runtime dir
   * preserve the outer parent display variables needed to open the nested window

3. Launch `niri` with:

   * `niri --config <fixture-path>`

4. **Do not use `--session`**
   The official docs say `--session` imports environment variables globally into the session manager and D-Bus and starts session services. That is exactly what you do not want in isolated nested tests. ([GitHub][2])

5. Capture stdout/stderr to files.

6. Poll for readiness by:

   * discovering a socket under the isolated runtime dir
   * verifying it with a real `VersionRequest()` through `niri-pypc`

That last step is ideal because it proves the exact IPC boundary your library actually uses. The niri IPC docs describe the JSON-over-socket contract directly, and the event stream is part of that same stable boundary. ([GitHub][1])

## 9. Always use explicit `socket_path` in nested tests

Your library config resolves socket path via explicit `socket_path` first and `NIRI_SOCKET` second. For nested tests, always pass the discovered socket path explicitly:

```python
config = NiriConfig(socket_path=harness.socket_path)
```

Do **not** rely on ambient `NIRI_SOCKET` inside the pytest process.

That gives you the strongest guarantee that nested tests cannot leak onto the host compositor socket. 

## 10. Write hermetic KDL fixtures, not copies of the default config

Each KDL fixture should be:

* minimal
* deterministic
* free of external startup programs
* commented with the intended test invariants

Do not lift the upstream default config wholesale. Recent niri releases note that the default config now spawns Waybar at startup, which is bad for deterministic tests. Strip all startup spawns, bars, lock/idle tools, and anything session-global. ([GitHub][3])

Practical rules:

* `base-minimal.kdl`: one output, one active workspace, no startup clients
* `multi-output.kdl`: only if your nested backend can actually expose multiple outputs
* `dense-workspace.kdl`: designed for larger snapshot payloads, but still no nondeterministic startup extras

## 11. Use scenario manifests for assertions, not hardcoded expectations in tests

Each YAML file should hold the invariants that belong to the fixture, such as:

```yaml
key: minimal
config_fixture: base-minimal.kdl
runtime:
  startup_timeout_s: 15
  ready_probe_interval_s: 0.1
  settle_delay_s: 0.25
  event_timeout_s: 3
capabilities:
  requires_multi_output: false
expectations:
  min_outputs: 1
  min_workspaces: 1
  allow_zero_windows: true
  output_names: []
  workspace_output_map: {}
```

That keeps test code generic and makes config drift obvious.

## 12. Implement the `minimal` scenario first and stabilize it

Add `tests/integration/test_nested_niri_basic.py` with `@pytest.mark.nested` and `@pytest.mark.niri_scenario("minimal")`.

Start with four tests:

1. `test_nested_version_request_round_trip`
2. `test_nested_outputs_snapshot_matches_manifest`
3. `test_nested_workspaces_snapshot_matches_manifest`
4. `test_nested_windows_request_decodes_on_nested_socket`

For `Windows`, do not require non-empty windows at startup. The plan says verify request/reply round-trips; that can be satisfied with a valid decoded response even when the list is empty. 

## 13. Add event tests, but use real IPC actions where possible

The IPC docs say the event stream gives complete current state up front and then follows with updates. Build around that. ([GitHub][1])

In `tests/integration/test_nested_niri_events.py`:

* open a real `NiriEventStream`
* assert you receive initial state/event bootstrap
* use `ActionRequest`-based operations to trigger workspace/focus changes where possible
* assert the resulting event types and minimal invariants

This is much better than depending on arbitrary UI input simulation.

## 14. Treat `multi-output` as capability-aware, not blindly mandatory

This is the one place where I would be strict about realism: nested backends do not always expose multiple outputs in a way your CI can count on.

So implement `multi-output` like this:

* start nested niri with the `multi-output` scenario
* after readiness, query `Outputs`
* if the scenario requires multi-output and the backend exposes fewer than expected, **skip with a clear reason**
* if it does expose multiple outputs, run the full mapping/event assertions

That gives you deterministic behavior instead of flaky red builds.

## 15. Split `dense-workspace` into two parts

The plan wants dense payloads plus burst/queue behavior. Those are not equally well suited to real nested E2E.

Use:

* **nested test** for real startup + large snapshot decoding
* **contract test** for synthetic burst/backpressure behavior using fake socket transcripts

This matches the plan’s own note that scenarios can pair with IPC fixtures for deterministic assertions. It is also the cleanest way to test queue pressure without depending on compositor timing accidents. 

## 16. Add failure artifact capture in pytest

In `tests/conftest.py`, add a `pytest_runtest_makereport` hook so failed nested tests retain:

* scenario key
* config fixture path
* isolated runtime dir
* discovered socket path
* startup timing summary
* last N log lines
* optional frame transcript snippets

That is directly called for in the plan’s CI artifact section. 

## 17. CI and local commands

Add scripts so everything stays runnable through `devenv shell -- ...`, exactly as required by the plan and the project spec.  

Use this split:

* `devenv shell -- pytest -m contract -q`
* `devenv shell -- pytest -m nested -q`
* `devenv shell -- pytest -m smoke -q`

CI should be:

* PR default: lint + typecheck + `contract`
* opt-in or nightly: `nested`
* release gate: `contract` + `nested` + manual smoke checklist

That is exactly the rollout and gating model in the plan. 

## 18. Definition of done for the implementation

You are done when all of these are true:

* all nested startup config comes only from `tests/fixtures/niri/configs/*.kdl`
* scenario selection works via marker and env override
* nested harness never uses the host `NIRI_SOCKET`
* `minimal` is stable locally and in CI
* `multi-output` is either stable or explicitly capability-skipped
* `dense-workspace` covers both large payload decoding and deterministic burst/backpressure behavior
* current fast socket-contract coverage remains fast and separate

That delivers the enhancement plan in full without sacrificing the existing fast test layers. 

[1]: https://github.com/niri-wm/niri/wiki/IPC?utm_source=chatgpt.com "IPC · niri-wm/niri Wiki"
[2]: https://github.com/YaLTeR/niri/wiki/Configuration%3A-Overview/46fe09742a6811789126ad08e6c8f52d93c025b6?utm_source=chatgpt.com "Configuration: Overview · niri-wm/niri Wiki · GitHub"
[3]: https://github.com/niri-wm/niri/discussions/1589?utm_source=chatgpt.com "v25.05 · niri-wm niri · Discussion #1589"
