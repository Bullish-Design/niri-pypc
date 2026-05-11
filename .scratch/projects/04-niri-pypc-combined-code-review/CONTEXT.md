# Context (2026-05-11)

Reviewed:
- NIRI_PYPC_CODE_REVIEW_FINAL.md
- NIRI_PYPC_REFACTOR_OPPORTUNITIES-FINAL.md

Validated claims directly against repository code and schemas:
- tools/normalize_ir.py has early primitive return that loses array/items, map/additionalProperties, and prefixItems tuple fidelity.
- IR and generated reply/models currently degrade key fields and nullable payload variants.
- event_stream lifecycle/close semantics have queue-full and terminal-cause ambiguity.
- client/bundle lifecycle usage is heavier than necessary; bundle mutates LifecycleManager private state.
- codec has class-name-prefix unwrap and raises DecodeError on encode path.
- strict_version_check config appears unused.

Net: both docs are directionally very strong; only a few framing/prioritization details need adjustment.

Update:
- Refined wording in both FINAL review docs to better match implementation direction:
  - Emphasized targeted correctness/alignment refactor over redesign framing.
  - Reframed tuple guidance to focus on preserving fixed-length `prefixItems` intent, without mandating tuple syntax everywhere.

Editorial pass:
- Calibrated modal language (must/should/required) across both docs.
- Preserved strict wording only where tied to correctness gates/invariants.
- Reduced absolutist wording in architecture and recommendation sections.
