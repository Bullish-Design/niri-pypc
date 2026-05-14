# Context

## Session Summary (2026-05-14)

Completed a deep codebase mapping pass and produced a new implementation guide:
- `.scratch/projects/11-action-refactor-review/ACTION_REFACTOR_CODE_REVIEW_REFACTOR_GUIDE.md`

Work performed:
- Read mandatory operating rules and project refactor report.
- Inspected target implementation modules in `src/niri_pypc` (transport, client, event stream, bundle, types base, actions).
- Inspected relevant generators (`tools/normalize_ir.py`, `tools/generate_types.py`).
- Inspected key tests and README usage/docs to map all required refactor touchpoints.

Guide output includes:
- strict phase ordering
- concrete file/function edit instructions
- test additions per review item
- regeneration/type-fidelity instructions
- final quality-gate command sequence
- intern checklist

## Next Logical Step

Execute the implementation phases from `ACTION_REFACTOR_CODE_REVIEW_REFACTOR_GUIDE.md` on a dedicated branch, commit-by-commit.
