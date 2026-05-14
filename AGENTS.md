# AGENTS.md

Read `.scratch/CRITICAL_RULES.md` first in every session, then `.scratch/REPO_RULES.md`.

Operational reminders:
- Never use subagents.
- Keep project tracking files in `.scratch/projects/<num>-<name>/` up to date.
- Use `devenv shell -- ...` for all environment-dependent CLI commands.
- This includes tests, project scripts, demos, linters/formatters/typecheckers, dependency sync, and app/runtime commands.
- Before the first test run in each session, sync dependencies:
  - `devenv shell -- uv sync --extra dev`

Test execution policy:
- Default test runs must exclude visual/demo and manual live smoke tests:
  - `devenv shell -- pytest -m "not visible_demo and not smoke"`
- Visible nested/visual tests are strict opt-in only.
- Do not run with `--nested-visible` unless the user explicitly requests visual testing.
- Do not set `NIRI_PYPC_ALLOW_VISIBLE_NESTED=1` unless the user explicitly requests visual testing.
- When explicitly requested, run visual tests with:
  - `NIRI_PYPC_ALLOW_VISIBLE_NESTED=1 devenv shell -- pytest -m visible_demo -s --nested-visible`

Available local skills:
- `.scratch/skills/python-linting-ruff/SKILL.md`
- `.scratch/skills/python-typecheck-ty/SKILL.md`

Quality gate checklist before finalizing Python changes:
1. Run `devenv shell -- ruff check .` for any Python edit.
2. Run `devenv shell -- ruff format --check .` for any Python edit.
3. Run `devenv shell -- ty check .` when changing signatures, typed models, protocol/contracts, or public interfaces.
4. Run targeted tests for changed behavior; run the full suite when changes are cross-cutting.
5. If checks fail, fix and rerun until clean; mention any unresolved blockers explicitly.
