# PLAN

## Goal
Implement actionable fixes from `Niri-PyPC_Focused_Deep-Research-Report.md` and capture E2E testing strategy informed by `niri-docs-developing-overview.md`.

## Steps
1. Reproduce and fix transport frame-size bug so configured `max_frame_size` is actually enforceable above asyncio default limits.
2. Add regression tests covering large-frame accept/reject paths and stream behavior where relevant.
3. Implement low-risk packaging/docs hardening from report (license file and metadata links if missing).
4. Create `E2E_TESTING_IDEAS.md` with practical, staged E2E strategy for this library.
5. Run required quality gates and targeted tests, then full checks if needed.

## Acceptance Criteria
- Large valid frames (well above 64 KiB) are accepted when below configured `max_frame_size`.
- Oversized frames raise `ProtocolError` deterministically.
- New/updated tests pass.
- `E2E_TESTING_IDEAS.md` exists with actionable scenarios, tooling, and CI plan.
- Required lint/format/type checks are clean for Python changes.
