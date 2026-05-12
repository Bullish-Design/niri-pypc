# VISUAL_TEST_SUITE_HARDENING_GUIDE

## Table of Contents

1. Scope and Safety Goal
2. Current Risk Map in This Repository
3. Implementation Sequence
4. Step 1: Add Fail-Closed Visible Preflight
5. Step 2: Require Explicit Unsafe Opt-In for Visible Mode
6. Step 3: Enforce PID-Strict IPC Socket Discovery in Visible Mode
7. Step 4: Add Single-Runner Session Guard Lock
8. Step 5: Add a Visible-Mode Circuit Breaker
9. Step 6: Strengthen Cleanup Semantics for Child Process Groups
10. Step 7: Enforce Serial Execution for Visible Runs
11. Verification Plan
12. Rollout Plan
13. Troubleshooting Notes

## 1) Scope and Safety Goal

This guide hardens visible/nested `niri` tests to fail closed and minimize risk to the developer's running Wayland session.

Primary goal:
- Prevent repeated unsafe launch attempts and ambiguous socket attachment behavior.
- Ensure visible-mode tests either run in a clearly valid environment or skip immediately with precise diagnostics.

Non-goal:
- Absolute guarantee against upstream compositor/runtime bugs. The safety objective is strict guardrails and fast abort behavior in this test harness.

## 2) Current Risk Map in This Repository

Primary files to modify:
- `tests/helpers/nested_niri.py`
- `tests/conftest.py`
- optional docs update in `README.md`

Key current risk vectors:
- Visible mode shares parent runtime namespace.
- Socket scan can still fallback to "new unknown socket" behavior.
- No global preflight gate for visible runs.
- No explicit single-run lock for visible mode.
- No circuit breaker to stop repeated visible relaunches after first compositor-level failure.
- Cleanup should remain strictly bounded to launched child session/process group.

## 3) Implementation Sequence

Implement in this exact order:
1. Fail-closed preflight.
2. Explicit unsafe opt-in gate.
3. PID-strict socket discovery in visible mode.
4. Session guard lock for visible mode.
5. Circuit breaker on compositor/backend startup failures.
6. Cleanup hardening (process group aware).
7. Serial-only enforcement for visible mode.

Reason:
- Steps 1/2 are lowest-risk and immediately reduce accidental harm.
- Steps 3/4/5 remove ambiguity and repeated pressure on compositor socket lifecycle.
- Steps 6/7 tighten execution behavior and reduce race risk.

## 4) Step 1: Add Fail-Closed Visible Preflight

### 4.1 Add a dedicated preflight function

In `tests/helpers/nested_niri.py`, add:
- `def _visible_preflight(self, env: dict[str, str]) -> tuple[bool, str]:`

Checks:
1. `WAYLAND_DISPLAY` is non-empty.
2. `XDG_RUNTIME_DIR` is non-empty.
3. `Path(XDG_RUNTIME_DIR) / WAYLAND_DISPLAY` exists and `is_socket()`.
4. Optional: reject if `XDG_SESSION_TYPE != "wayland"` when set.

Return:
- `(True, "")` when safe.
- `(False, "<actionable reason>")` otherwise.

### 4.2 Apply preflight before spawn

In `start(...)`, before `subprocess.Popen(...)` when `visible=True`:
- run `_visible_preflight(env)`.
- on failure: raise `RuntimeError(f"Visible preflight failed: {reason}")`.

### 4.3 Expected behavior

- Visible run should skip immediately (through fixture error handling) when socket is invalid.
- No nested niri process should be launched in that case.

## 5) Step 2: Require Explicit Unsafe Opt-In for Visible Mode

### 5.1 Add opt-in flag

Use env var:
- `NIRI_PYPC_ALLOW_VISIBLE_NESTED=1`

### 5.2 Enforce in fixture

In `tests/conftest.py` inside `nested_niri` fixture:
- if `visible=True` and env var is not `1`, call:
  - `pytest.skip("Visible nested mode requires NIRI_PYPC_ALLOW_VISIBLE_NESTED=1")`

### 5.3 Optional CLI gate

Add `--nested-visible-unsafe` (boolean) and require either:
- CLI unsafe flag, or
- env opt-in.

Prefer env-only if you want fewer moving parts.

### 5.4 Expected behavior

- Accidental `--nested-visible` runs in normal terminals do not execute unless operator intentionally opts in.

## 6) Step 3: Enforce PID-Strict IPC Socket Discovery in Visible Mode

### 6.1 Current problem

Visible mode scans parent runtime namespace with many sockets. Any fallback that accepts "new unknown socket" is unsafe.

### 6.2 Change wait logic

In `_wait_for_socket(...)`, add a `strict_pid: bool` flag.

Behavior:
- Always prefer `f".{pid}.sock" in filename`.
- If `strict_pid=True`, never return fallback sockets.
- If timeout reached without PID match, return `None`.

Call with:
- `strict_pid=True` for visible mode.
- `strict_pid=False` for isolated/non-visible mode.

### 6.3 Logging

When debug enabled:
- print whether strict mode is active.
- print matched socket path.

### 6.4 Expected behavior

- Visible tests only attach to IPC socket produced by the just-launched nested process.

## 7) Step 4: Add Single-Runner Session Guard Lock

### 7.1 Lock path

Use one lock path for visible runs, for example:
- `/tmp/niri-pypc-visible-nested.lock`

### 7.2 Lock mechanism

At visible run setup (fixture scope):
- open lock file and acquire non-blocking exclusive lock via `fcntl.flock`.
- if lock acquisition fails:
  - `pytest.skip("Visible nested tests already running in another process/session")`

Release lock in fixture teardown.

### 7.3 Why lock in fixture (not harness)

Fixture-level lock avoids repeated lock acquisition per test and makes skip behavior deterministic for the entire run.

### 7.4 Expected behavior

- Two visible test runs cannot operate concurrently.
- Reduces compositor/session race pressure.

## 8) Step 5: Add a Visible-Mode Circuit Breaker

### 8.1 Purpose

On first compositor/backend startup failure, stop launching additional visible nested instances in that pytest session.

### 8.2 Add breaker state

In `NestedNiriHarness`:
- `self._visible_circuit_open: bool = False`
- `self._visible_circuit_reason: str = ""`

### 8.3 Open breaker on critical startup failures

If startup fails and stderr indicates compositor/backend failures (e.g. contains):
- `WaylandError(Connection(NoCompositor))`
- `EventLoopCreation(`
- `cannot open display`

Then:
- set `self._visible_circuit_open = True`
- record reason.

### 8.4 Honor breaker before launch

At start of `start(...)` when `visible=True`:
- if breaker open: raise `RuntimeError(f"Visible circuit open: {reason}")`

Fixture will convert to skip.

### 8.5 Expected behavior

- One hard failure => no repeated visible relaunch storm.

## 9) Step 6: Strengthen Cleanup Semantics for Child Process Groups

### 9.1 Capture process group data

After spawn:
- store child pid + pgid in instance metadata.

Update dataclass `NestedNiriInstance` with:
- `pid: int`
- `pgid: int | None = None`

### 9.2 Group-aware termination

In `stop(...)`:
1. Try graceful terminate to child process group:
   - `os.killpg(pgid, signal.SIGTERM)` when pgid available.
2. wait timeout.
3. escalate to `SIGKILL` group only if needed.

Important:
- only target child process group created by this harness.
- never broadcast to parent session.

### 9.3 Cleanup bounds

Keep cleanup restricted to `instance.runtime_dir` (already correct).
Do not remove or mutate parent runtime paths.

### 9.4 Expected behavior

- Better cleanup for child trees (xwayland helpers, etc.) with strict scope boundaries.

## 10) Step 7: Enforce Serial Execution for Visible Runs

### 10.1 Detect xdist/parallel mode

In fixture or `pytest_configure`:
- if `visible=True` and `PYTEST_XDIST_WORKER` exists:
  - skip with message.
- if `-n` detected as >1 (where available), fail fast or skip visible tests.

### 10.2 Optional test selection rule

For visible mode, restrict to a dedicated marker subset (recommended):
- add marker `visible_demo`
- only a minimal curated set uses it.

Command:
- `pytest -m visible_demo --nested-visible ...`

### 10.3 Expected behavior

- No parallel visible compositor startup attempts.
- Predictable, low-churn developer demo runs.

## 11) Verification Plan

Run after implementing steps 1-7:

1. Static quality:
- `devenv shell -- ruff check .`
- `devenv shell -- ruff format --check .`
- `devenv shell -- ty check .`

2. Guardrail behavior:
- visible without opt-in => skip with explicit message.
- visible with broken socket env => immediate preflight skip, no spawn.
- parallel visible invocation => one run skips due lock.
- forced compositor failure => first failure opens breaker; subsequent tests skip without spawn.

3. Functional visible run:
- with healthy session and opt-in:
  - single visible test passes or fails functionally, but does not destabilize socket/session.

## 12) Rollout Plan

1. Implement steps 1-3 and verify.
2. Implement steps 4-5 and verify skip/circuit behavior.
3. Implement steps 6-7 and verify cleanup/serial protections.
4. Add README section for safe visible mode command and opt-in requirements.
5. Add a short "Incident recovery" section for developers:
   - how to detect stale socket state
   - when to relogin/restart session

## 13) Troubleshooting Notes

- If `ss` shows `wayland-*` but `test -S $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY` fails, treat as socket/session inconsistency; skip visible tests and recover session before retry.
- `wayland-info` absent (`127`) is a tooling gap, not a compositor proof.
- Keep `NIRI_PYPC_NESTED_DEBUG=1` for actionable startup diagnostics.
- Use `NIRI_PYPC_KEEP_NESTED_ARTIFACTS=1` only for debugging; disable for normal runs to avoid runtime-dir clutter.
