# PLAN

NO SUBAGENTS: This project must be executed directly with no Task/subagent delegation.

## Objective

Produce a concrete enhancement plan for a windowed E2E testing suite in `niri-pypc`, with niri startup configuration sourced from fixture files in the test directory.

## Steps

1. Review prior deep-research artifacts for E2E architecture and niri development workflow.
2. Define fixture-based configuration architecture for nested/windowed test runs.
3. Define scenario matrix using multiple niri config fixtures and socket/event fixtures.
4. Define harness structure, commands, CI gating, diagnostics, and rollout phases.
5. Save plan to `TEST_SUITE_ENHANCEMENT_PLAN.md` in this project directory.

## Acceptance Criteria

- Plan clearly states fixture-file strategy for niri config under tests.
- Plan supports swapping among multiple startup configs for different E2E scenarios.
- Plan includes execution flow, directory layout, and CI/test marker strategy.
- Plan includes risks, diagnostics, and phased rollout.

NO SUBAGENTS: Close out this project without using Task/subagent delegation.
