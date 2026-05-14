# ACTION_REFACTOR_CONCEPT_REVIEW

Reviewer: Claude (senior review)
Concept under review: `ACTION_REFACTOR_CONCEPT.md`

---

## Executive Summary

The concept correctly identifies the core pain point (verbose 3-level nesting to construct action requests) and proposes a reasonable additive approach. However, it has several significant gaps: it under-addresses the nested enum ergonomics that make up most of the actual friction, bundles an unrelated compatibility surface into the scope, and proposes an over-engineered module layout for what should be a thin convenience layer. The builder return type and naming strategy need refinement.

Overall assessment: **Revise before implementation.** The core idea is sound but the execution plan needs tightening.

---

## Section-by-Section Review

### Section 1: Purpose and Scope

**Verdict: Mostly good, but scope is too broad.**

The concept bundles two unrelated features:
1. Action helper builders (ergonomic constructors)
2. Metadata compatibility surface (`niri_pypc.compat`)

These solve different problems for different consumers. The compat surface has no dependency on the action helpers and vice versa. Bundling them inflates the concept scope, splits reviewer attention, and creates a false coupling between two independent deliverables.

**Recommendation:** Split `niri_pypc.compat` into its own concept document. This review will focus primarily on the action helper layer, which is the actual "action refactor."

### Section 2: Current State in niri-pypc

**Verdict: Incomplete analysis of the actual friction.**

The concept identifies three pain points but misses the most important structural detail. The actual construction path for an action request is **three levels of wrapping**:

```python
# Current: 3 levels of nesting
ActionRequest(
    payload=Action(
        root=MoveWindowToWorkspaceAction(
            reference=WorkspaceReferenceArg(
                root=NameWorkspaceReferenceArg(payload="browser")
            ),
            focus=True,
        )
    )
)
```

The concept's pain-point list says "common action construction is verbose" but doesn't break down *where* the verbosity comes from:

1. `ActionRequest(payload=...)` wrapper (mechanical, always identical)
2. `Action(root=...)` wrapper (mechanical, always identical)
3. The action variant class itself (this is the actual domain content)
4. **Nested enum arguments** like `WorkspaceReferenceArg`, `SizeChange`, `PositionChange`, `LayoutSwitchTarget` — each requiring their own `EnumType(root=VariantType(payload=...))` construction

Points 1-2 are trivially solved by any builder. **Point 4 is where real user friction lives**, and the concept barely addresses it.

### Section 3: Design Goals

**Verdict: Good.**

The six goals are well-prioritized. Non-goals are appropriate. No issues.

### Section 4: Proposed Public API Additions

**Verdict: Significant design issues.**

#### 4.1 Action helpers — return type problem

The concept proposes builders return `ActionRequest`. This is the correct final type for `NiriClient.request()`, but it's the **wrong abstraction boundary** for the builder layer.

Consider: `ActionRequest` is a request-level concept. The builder is constructing an *action*, not a request. The wrapping from action → request is mechanical (`ActionRequest(payload=Action(root=action))`). If builders return `ActionRequest`, they conflate two concerns:
- What action to perform (domain logic)
- How to package it for the request protocol (transport concern)

**Better approach:** Builders should return `Action` (the externally-tagged enum). Then provide a single utility or let the client accept `Action` directly. This gives consumers flexibility to inspect/compose actions before submitting them.

Alternatively, if the goal is strictly "one function call to a sendable object," returning `ActionRequest` is acceptable, but the concept should explicitly justify this and acknowledge the tradeoff.

#### 4.1 — Missing ergonomic wrappers for nested enums

The proposed API signatures expose raw generated types as parameters:

```python
focus_workspace(reference: WorkspaceReferenceArg) -> ActionRequest
```

But `WorkspaceReferenceArg` is itself an externally-tagged enum requiring nested construction:

```python
# User still has to write this:
focus_workspace(
    reference=WorkspaceReferenceArg(root=NameWorkspaceReferenceArg(payload="browser"))
)
```

This eliminates the `ActionRequest(payload=Action(root=...))` boilerplate but preserves the *parameter-level* boilerplate, which is equally painful. The concept should address this in one of these ways:

- **Option A — Overloaded parameters:** Accept `str | int` directly and construct the workspace reference internally:
  ```python
  focus_workspace("browser")           # by name
  focus_workspace(3)                   # by index
  focus_workspace(ws_id=42)            # by id
  ```

- **Option B — Separate reference helpers:** Provide `workspace_by_name()`, `workspace_by_index()`, `workspace_by_id()` that return `WorkspaceReferenceArg`.

- **Option C — Accept the generated type as-is** and document the nesting. This is the least ergonomic option and undermines the purpose of the helper layer.

The same issue applies to `SizeChange`, `PositionChange`, and `LayoutSwitchTarget` parameters. The concept must address this or the helpers will feel half-finished.

#### 4.1 — Example function list gaps

The concept lists 8 example builders but there are **138 action variants**. The concept doesn't define:
- Selection criteria for the MVP set (what makes an action "high-value"?)
- Whether remaining actions get builders later or are intentionally left as direct-construction-only
- How to handle the ~60 parameterless unit-like actions (e.g., `FocusColumnLeftAction`, `MoveWindowDownAction`) — do these even need builders, or is `Action(root=FocusColumnLeftAction())` simple enough?

**Recommendation:** Categorize actions into tiers:
1. **Tier 1 — builders needed:** Actions with complex parameters (nested enums, multiple fields). ~20-30 actions.
2. **Tier 2 — simple re-exports sufficient:** Actions with 0-1 simple parameters. A flat function adds minimal value over direct construction.
3. **Tier 3 — rare/debug actions:** Skip initially (`DebugToggleDamage`, `ShowHotkeyOverlay`, etc.).

#### 4.2 Compat surface

As noted above, this should be a separate concept. Brief feedback:
- The model design is reasonable
- `SchemaKind` as an enum is correct
- Version parsing is a known hard problem; the concept correctly identifies this but underestimates the effort
- `build_compat_report()` is premature — start with individual check functions only

### Section 5: Action Helper Architecture

**Verdict: Over-engineered module layout.**

#### 5.1 Proposed file structure

```
src/niri_pypc/actions/__init__.py
src/niri_pypc/actions/builders.py
src/niri_pypc/actions/presets.py  (optional)
```

For a set of 8-12 thin wrapper functions, a full package with multiple modules is unnecessary. A single module is sufficient:

```
src/niri_pypc/actions.py
```

If it grows beyond ~500 lines, *then* promote to a package. Starting with a package adds import complexity and file navigation overhead for no benefit.

#### 5.2 Builder rules

Good. The four rules (deterministic, side-effect-free, return generated types, no client coupling) are correct and should be preserved.

#### 5.3 Naming and stability policy

The naming policy says "use snake_case function names matching user intent, not generated class names." But the examples given (`focus_workspace`, `move_window_to_workspace`, `toggle_window_floating`) are just snake_case versions of the generated class names with the `Action` suffix dropped. This is fine — it means the naming policy is actually "snake_case the wire name," which is simpler and more predictable than "match user intent."

**Recommendation:** State the rule precisely: function names are the action's wire name converted to snake_case. This is deterministic, predictable, and automatable.

#### 5.4 Presets

Premature. Remove from the concept entirely. The concept itself says "only be added once real use-cases exist," which means it shouldn't be in a concept document for initial implementation. Including it invites scope creep.

### Section 6: Metadata Compatibility Surface Architecture

**Verdict: Out of scope — defer to separate concept.**

The design is reasonable in isolation but doesn't belong in this document. See Section 1 comments.

### Section 7: Backward Compatibility Strategy

**Verdict: Good. No issues.**

The additive approach is correct. Not deprecating existing imports initially is the right call.

### Section 8: Implementation Plan (Phased)

**Verdict: Phase 1 is reasonable; Phases 2-4 have issues.**

Phase 1 exit criteria ("typical workspace/window orchestration actions are constructible without touching generated classes") is good but should add: "including their parameter types" — otherwise the nested enum problem means users still touch generated classes for parameters.

Phase 2-3 should be removed from this concept (compat surface).

Phase 4 is vague. "Collect downstream feedback" is not an implementation phase — it's ongoing maintenance.

**Revised phasing for action helpers only:**

1. **Phase 1:** Core builder module + nested enum convenience constructors for `WorkspaceReferenceArg`, `SizeChange`, `PositionChange`. Tests.
2. **Phase 2:** Expand builder coverage based on downstream usage data. Add to package root exports.
3. **Phase 3:** Evaluate whether `NiriClient` should gain convenience methods (open question #4 from the concept).

### Section 9: Testing Strategy

**Verdict: Mostly good, one important gap.**

The proposed test patterns (type assertion, variant assertion, field mapping assertion) are correct. Missing:

- **Wire format assertion:** For each builder, verify the *serialized JSON output* matches expected wire format. This catches subtle issues where the builder produces a valid Python object that serializes incorrectly. Example:
  ```python
  req = spawn(["alacritty"])
  wire = Request(root=req).model_dump_json()
  assert json.loads(wire) == {"Action": {"Spawn": {"command": ["alacritty"]}}}
  ```

- **Round-trip with existing codec tests:** Ensure builder outputs are compatible with the existing `test_roundtrip.py` infrastructure.

### Section 10: Documentation and Migration Guidance

**Verdict: Reasonable but premature for a concept document.**

Docs changes should be specified in the PR, not the concept. Keep the concept focused on architecture and API design decisions.

### Section 11: Risks and Mitigations

**Verdict: Good coverage.**

One additional risk not identified:

- **Risk: helpers obscure the protocol learning curve.** New users who only use helpers may not understand the underlying protocol structure, making debugging harder when helpers don't cover their use case.
- **Mitigation:** Docstrings on each helper should reference the generated class it wraps, e.g., `"""Wraps SpawnAction. See niri_pypc.types.generated.action.SpawnAction for full protocol details."""`

### Section 12: Open Questions

**Verdict: Question framing needs improvement.**

> **Q1:** Should `actions` return `ActionRequest` objects or raw `Action` payloads plus a separate wrapper helper?

This is the most important design decision and should be resolved *in the concept*, not left open. See my analysis in Section 4.1. My recommendation: return `ActionRequest` for simplicity (users want one function call → sendable object), but document this as a deliberate choice.

> **Q2:** Do we want a dedicated exception type for compatibility failures?

Out of scope (compat surface).

> **Q3:** Should schema compatibility checks support partial-match policies?

Out of scope (compat surface).

> **Q4:** Should we include convenience `client.request_action(...)` overloads now?

This is worth discussing here. The concept should take a position. My recommendation: **defer.** Adding a method to `NiriClient` couples the helper layer to the transport layer, which contradicts Design Goal 6 ("keep implementation lightweight") and Builder Rule 4 ("builders must not call NiriClient directly"). If the action builders are ergonomic enough, a thin `client.request(spawn(["alacritty"]))` is already clean.

### Section 13: Suggested Initial Patch Set

**Verdict: Too many PRs for the scope.**

Three PRs for what amounts to one module of 8-12 functions and their tests is over-segmented. If the compat surface is split out:

- **PR 1:** `src/niri_pypc/actions.py` (or `actions/` if justified), tests, package root re-export. Done.

One PR keeps the review atomic and the diff coherent.

---

## Cross-Cutting Concerns

### Missing: `OutputRequest` coverage

The concept focuses entirely on `ActionRequest` but ignores `OutputRequest`, which has its own `OutputAction` enum with 9 variants (`ModeOutputAction`, `ScaleOutputAction`, `VrrOutputAction`, etc.). These are equally verbose to construct:

```python
OutputRequest(
    output="eDP-1",
    action=OutputAction(root=ScaleOutputAction(scale=ScaleToSet(root=SpecificScaleToSet(payload=2.0))))
)
```

If the goal is "downstream libraries don't need to construct raw generated variants for common workflows," output configuration is in scope. The concept should either:
- Include output action helpers in the builder set, or
- Explicitly state that `OutputRequest` helpers are out of scope and why.

### Missing: Type exports strategy

The concept doesn't specify what the new module's `__all__` should contain, or how the package root `__init__.py` should re-export the new surface. Currently `niri_pypc.__init__` exports only client/config/error classes. Should `spawn`, `focus_workspace`, etc. be top-level imports? Or must users `from niri_pypc.actions import spawn`?

**Recommendation:** Do not add builders to the package root `__all__`. Keep them namespaced under `niri_pypc.actions` to avoid polluting the top-level namespace with 100+ function names as the surface grows.

### Missing: Handling `focus` parameter defaults

Several action variants have a `focus: bool` parameter with no default (e.g., `MoveWindowToWorkspaceAction`, `MoveColumnToWorkspaceAction`). The concept's example signatures don't show whether builders provide a default:

```python
# Generated: focus is required (no default)
class MoveWindowToWorkspaceAction(ProtocolVariant):
    focus: bool
    reference: WorkspaceReferenceArg
    window_id: int | None = None
```

The builder should decide: does `move_window_to_workspace()` default `focus=True`? This is a UX decision the concept should document. Defaulting `focus=True` matches niri CLI behavior and is almost always what users want.

---

## Summary of Required Changes Before Implementation

### Must fix:
1. **Split compat surface** into separate concept document.
2. **Address nested enum ergonomics** — define how `WorkspaceReferenceArg`, `SizeChange`, `PositionChange` parameters are simplified in the builder API.
3. **Resolve open question #1** (return type) in the concept, not at implementation time.
4. **Define action selection criteria** for the MVP builder set.

### Should fix:
5. **Simplify module layout** — single module unless size justifies package.
6. **Remove presets** section entirely.
7. **Add wire-format test pattern** to testing strategy.
8. **Address `OutputRequest`** coverage explicitly (in or out of scope).
9. **Define default values** for `focus: bool` and similar required-but-predictable parameters.

### Nice to have:
10. Specify `__all__` / export strategy for new module.
11. Add "references generated class" policy for docstrings.
12. Consolidate PR plan to single PR for action helpers.
