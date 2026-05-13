# Issues

## ISSUE_001: `ty check` baseline failures

Status: Open (pre-existing)

Observed during Step 1 validation:
- `src/niri_pypc/types/base.py`: unresolved attribute `payload` on generic intersections.
- `src/niri_pypc/types/codec.py`: unknown keyword args and unresolved `payload` attributes.

Impact:
- Blocks a fully clean `ty check .` gate unless addressed in later steps.
