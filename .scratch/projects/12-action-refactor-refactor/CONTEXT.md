# CONTEXT

- Phase 5 complete: type/schema fidelity and generation updates applied.
- Implemented:
  - Recorded T-4 tuple strategy decision in `.scratch/projects/11-action-refactor-review/DECISIONS.md`.
  - `tools/normalize_ir.py`: `prefixItems` now always normalize to tuple IR for non-empty fixed-length arrays.
  - Regenerated IR and generated type outputs.
  - `src/niri_pypc/types/base.py`: hardened newtype serializer branch to require payload attribute presence.
  - `tools/generate_types.py`: removed dead overwritten assignment in `gen_all_unit_str_enum_code`.
  - Type tests updated for tuple fidelity (`physical_size`, `WindowLayout` tuple fields) and tuple-length validation.
  - Added base runtime guard coverage for missing-payload newtype serialization path.
- Validation:
  - `devenv shell -- pytest tests/types -q` ✅
  - `devenv shell -- verify-generated` ✅
  - `devenv shell -- ty check .` ❌ pre-existing unrelated diagnostics in `src/niri_pypc/types/codec.py`.
- Next: Phase 6 actions module lint/safety documentation cleanup.
