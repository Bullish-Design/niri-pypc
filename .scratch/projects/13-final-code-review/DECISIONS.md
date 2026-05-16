# Decisions

## 2026-05-15: Consolidate enum encode path via codec
- `ExternallyTaggedEnum._encode_root` now delegates to `encode_externally_tagged`.
- Rationale: removes duplicated encode logic, ensures newtype payloads use consistent JSON serialization, and standardizes on `EncodeError` behavior.

## 2026-05-15: Fail fast on unknown JSON schema shapes in IR normalization
- `canonical_type` now raises `ValueError` instead of silently returning `"string"` fallback.
- Rationale: prevents silent type degradation and surfaces upstream schema changes explicitly.
