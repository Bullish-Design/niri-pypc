# Python Linting (Ruff)

Use this skill when changing Python code in this repo and you need linting/formatting to match project requirements.

## Required Tools
- `ruff` for linting and formatting.
- Run through devenv: `devenv shell -- ...`

## Canonical Commands
- Lint: `devenv shell -- ruff check .`
- Lint with autofix: `devenv shell -- ruff check --fix .`
- Format: `devenv shell -- ruff format .`
- Format check only: `devenv shell -- ruff format --check .`

## Scope
- Lint and format these paths by default: `src` and `tests`.
- If those directories do not exist yet, run Ruff on the Python paths that do exist.

## Configuration Source
- Ruff config lives in `pyproject.toml` under:
  - `[tool.ruff]`
  - `[tool.ruff.lint]`
  - `[tool.ruff.format]`

## Enforcement
- Before finalizing substantial Python edits, run at least:
  1. `devenv shell -- ruff check .`
  2. `devenv shell -- ruff format --check .`
