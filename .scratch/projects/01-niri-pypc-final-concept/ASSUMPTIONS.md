# ASSUMPTIONS

1. `niri-pypc` is intended as the pinned protocol/runtime substrate, not a state-reduction engine.
2. `niri-state` is a separate downstream library that consumes typed events from `niri-pypc`.
3. The final concept should prioritize correctness, determinism, and reviewability over feature breadth.
4. The document should be implementation-guiding, not merely aspirational.
5. Current work is documentation and project-structure only; no runtime code edits are requested.
