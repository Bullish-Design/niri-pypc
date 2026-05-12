# Decisions

## 2026-05-12

1. Create a dedicated planning project directory before implementation.
- Rationale: aligns with project tracking rules and preserves continuity for follow-on implementation work.

2. Use fixture files within the test tree as the canonical source for niri E2E startup config.
- Rationale: makes starting state auditable, diffable, and easy to swap for scenario coverage.

3. Keep this project focused on a concrete enhancement plan document (`TEST_SUITE_ENHANCEMENT_PLAN.md`).
- Rationale: user requested a planning template deliverable, not immediate test harness code changes.
