# Decisions

## 2026-05-14 — Produce Refactor-Execution Guide Instead of Code Changes

- Decision: Create a detailed implementation guide (`ACTION_REFACTOR_CODE_REVIEW_REFACTOR.md`) without modifying production code.
- Rationale: User explicitly requested a thorough step-by-step refactoring guide derived from the existing review and current codebase state.
- Impact: Provides a concrete execution blueprint for upcoming implementation work while preserving current behavior in this task.

## 2026-05-14 — T-4 Fixed-Length Arrays Use Tuple IR Always

- Decision: Represent non-empty `prefixItems` arrays as tuple IR types unconditionally (`tuple<T1,T2,...>`), including homogeneous fixed-length shapes.
- Rationale: JSON Schema `prefixItems` expresses positional, fixed-length semantics; `array<T>` loses length/position guarantees and weakens generated type fidelity.
- Impact: Generated Pydantic models gain tuple typing for fixed-length fields, improving static accuracy and runtime validation guarantees.
