# REPO RULES — niri-pypc

## ABSOLUTE RULES — READ FIRST

1. **NO SUBAGENTS** — NEVER use the Task tool. Do ALL work directly.
2. **KEEP TRACKING CURRENT** — Maintain `.scratch/projects/<num>-<name>/` files while working.

---

Repo-specific standards and conventions. Loaded after `CRITICAL_RULES.md`.

## Project Scope

This repository builds `niri-pypc`, a Python library for controlling and integrating with the Niri compositor.

Current priority:
- keep the package/tooling setup coherent and reproducible
- enforce linting with Ruff and type checking with Ty
- keep config/docs aligned with repository naming and paths

## Environment and Tooling (MANDATORY)

Use `devenv shell --` for commands that execute project code or tooling.
You do not need it for read-only inspection commands (`ls`, `cat`, `rg`, `git show`, etc.).

Before the first test run in every session:
```bash
devenv shell -- uv sync --extra dev
```

Never use `uv pip install` in this repo.

Preferred quality commands:
```bash
devenv shell -- ruff check .
devenv shell -- ruff check --fix .
devenv shell -- ruff format .
devenv shell -- ruff format --check .
devenv shell -- ty check .
devenv shell -- pytest -q
```

## Protocol and Architecture Rules

- Treat the Atuin-facing protocol as the stable external boundary.
- Keep request and stream translation explicit and testable.
- Preserve SSE framing semantics (`text`, `done`, `error`) and avoid ad-hoc event names.
- Keep v1 implementation text-only; do not introduce partial tool-call behavior unless explicitly requested.
- Prefer stateless per-request handling for concurrency unless a task requires session-state features.

## Testing Expectations

- Add or update tests with every behavior change.
- Prioritize translator, protocol-model, SSE-framing, and stream error-path tests.
- Include integration coverage for Atuin-shaped request -> streamed SSE response where feasible.

## Key Reference Files

| Document | Path |
|----------|------|
| Concept review | `.scratch/projects/00-niri-pypc-brainstorming/NIRI_PYPC_CONCEPT.md` |
| Architecture overview | `.scratch/projects/00-niri-pypc-brainstorming/niri-pypc-concept-tweaks.md` |
| Agent operating instructions | `AGENTS.md` |
