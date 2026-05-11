# PLAN

NO SUBAGENTS: This project will be executed directly in the main agent only.

## Goal
Create a final, consolidated `NIRI_PYPC_CONCEPT_FINAL.md` that merges the baseline concept and tweak decisions into one internally consistent specification.

## Steps
1. Review source concept and tweak documents and extract unresolved decisions.
2. Define explicit final decisions for boundaries, unknown policy, determinism, runtime mismatch handling, config, concurrency, and error taxonomy.
3. Draft final concept doc with a complete TOC, then fill sections in order.
4. Ensure repository/project tracking files capture assumptions, decisions, and completion state.

## Acceptance Criteria
- New numbered project directory exists with standard tracking files.
- `NIRI_PYPC_CONCEPT_FINAL.md` exists in the new directory.
- Document resolves prior ambiguities and contradictions.
- Layer boundary with `niri-state` is explicit and test/docs implications are covered.

NO SUBAGENTS: All work remains direct and local.
