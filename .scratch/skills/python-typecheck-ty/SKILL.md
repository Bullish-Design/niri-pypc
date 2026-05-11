# Python Type Checking (Ty)

Use this skill when Python edits may affect types, interfaces, or data models.

## Required Tool
- `ty` for type checking.
- Run through devenv: `devenv shell -- ...`

## Canonical Command
- Type check: `devenv shell -- ty check .`

## Configuration Source
- Ty config lives in `pyproject.toml` under:
  - `[tool.ty]`

## Scope
- Default type-check scope is `src`.
- If `src` is not present yet, adjust the command to target existing Python package paths.

## Enforcement
- Before finalizing substantial Python edits that change signatures or models, run:
  1. `devenv shell -- ty check .`
