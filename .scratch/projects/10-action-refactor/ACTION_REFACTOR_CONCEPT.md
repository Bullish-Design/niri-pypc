# ACTION_REFACTOR_CONCEPT

## Table of Contents

1. Purpose and Scope
   - Defines what this refactor is solving in `niri-pypc` and what is intentionally out of scope.
2. Current State in niri-pypc
   - Summarizes the current generated action/request surface and where consumers feel friction.
3. Design Goals
   - Establishes the primary API, compatibility, typing, and maintenance goals for the new surface.
4. Proposed Public API Additions
   - Describes the user-facing `actions` helper layer and the metadata compatibility API.
5. Action Helper Architecture
   - Explains module boundaries, naming conventions, and how helpers wrap generated models.
6. Metadata Compatibility Surface Architecture
   - Defines typed metadata models and compatibility checks built on generated metadata constants.
7. Backward Compatibility Strategy
   - Details how existing imports and generated classes remain valid while new APIs are added.
8. Implementation Plan (Phased)
   - Provides an incremental delivery plan with concrete code changes and milestones.
9. Testing Strategy
   - Specifies unit/integration coverage needed to keep behavior stable and maintain confidence.
10. Documentation and Migration Guidance
   - Lists docs and examples to publish so downstream projects can adopt the new surface safely.
11. Risks and Mitigations
   - Identifies technical and product risks with mitigation strategies.
12. Open Questions
   - Captures unresolved design choices that should be decided before implementation starts.
13. Suggested Initial Patch Set
   - A concrete first PR breakdown for starting execution of this concept.

## 1. Purpose and Scope

This concept proposes two related improvements to `niri-pypc`:

- Action refactor: add a stable, hand-written action helper layer so downstream libraries do not need to construct raw generated variants directly for common workflows.
- Metadata compatibility surface: add a public typed API exposing protocol generation metadata and compatibility checks, so downstream libraries can reason about version/schema compatibility without importing generated internals.

This concept is intentionally additive. It does not replace the generated protocol types under `src/niri_pypc/types/generated/` and does not alter transport behavior in `api/client.py` or `api/event_stream.py`.

Out of scope for this concept:

- Changes to wire protocol encoding/decoding.
- Regeneration format changes in `tools/generate_types.py`.
- Runtime policy decisions for higher-level reconcilers (for example spawn/match strategies).

## 2. Current State in niri-pypc

Current relevant structure:

- Generated action/request surface:
  - `src/niri_pypc/types/generated/action.py`
  - `src/niri_pypc/types/generated/request.py`
- Generated metadata constants:
  - `src/niri_pypc/types/generated/_metadata.py`
- Public re-export:
  - `src/niri_pypc/types/generated/__init__.py`
- Request execution path:
  - `src/niri_pypc/api/client.py`

Today, consumers typically do one of these:

- Import generated classes directly and build nested `ActionRequest(payload=...)` objects.
- Import from `niri_pypc.types.generated` wildcard exports and manually discover the right variants.

Pain points for downstream libraries:

- Common action construction is verbose and easy to get wrong.
- Generated class naming is mechanically correct but not ergonomically stable as a user API.
- Metadata exists, but only as constants in a generated module, so compatibility checks are ad hoc.

## 3. Design Goals

1. Preserve generated types as source-of-truth wire models.
2. Add a small ergonomic API that is stable across generator churn.
3. Keep all new public surfaces fully typed.
4. Make compatibility checks explicit, discoverable, and reusable.
5. Preserve backward compatibility with existing imports and request construction.
6. Keep implementation lightweight and testable.

Non-goals:

- Hiding all generated types forever.
- Introducing implicit behavior in request dispatch.
- Adding complex runtime negotiation with niri daemon versions.

## 4. Proposed Public API Additions

### 4.1 New package: `niri_pypc.actions`

Add a hand-written helper package for common action/request creation.

Proposed layout:

- `src/niri_pypc/actions/__init__.py`
- `src/niri_pypc/actions/builders.py`
- `src/niri_pypc/actions/presets.py` (optional, if wanted for grouped workflows)

Core API style:

- Builders return generated `ActionRequest` objects ready for `NiriClient.request(...)`.
- One function per common action with explicit parameters and sane defaults.

Examples:

- `spawn(cmd: list[str]) -> ActionRequest`
- `spawn_sh(command: str) -> ActionRequest`
- `focus_workspace(reference: WorkspaceReferenceArg) -> ActionRequest`
- `move_window_to_workspace(reference: WorkspaceReferenceArg, window_id: int | None = None) -> ActionRequest`
- `move_workspace_to_monitor(reference: WorkspaceReferenceArg, output: str) -> ActionRequest`
- `set_workspace_name(reference: WorkspaceReferenceArg, name: str) -> ActionRequest`
- `toggle_window_floating(window_id: int | None = None) -> ActionRequest`
- `fullscreen_window(window_id: int | None = None) -> ActionRequest`

### 4.2 New package: `niri_pypc.compat`

Add a typed metadata and compatibility API.

Proposed layout:

- `src/niri_pypc/compat/__init__.py`
- `src/niri_pypc/compat/models.py`
- `src/niri_pypc/compat/metadata.py`
- `src/niri_pypc/compat/checks.py`

Core API shape:

- `get_protocol_metadata() -> ProtocolMetadata`
- `is_schema_hash_known(kind: SchemaKind, expected_hash: str) -> bool`
- `check_minimum_upstream_version(min_version: str) -> CompatibilityResult`
- `check_exact_ir_hash(expected_ir_hash: str) -> CompatibilityResult`
- `build_compat_report(...) -> CompatibilityReport`

## 5. Action Helper Architecture

### 5.1 Separation of concerns

- Generated layer (`types/generated/*`): protocol fidelity and schema alignment.
- Action helper layer (`actions/*`): ergonomic constructors and stable naming.
- API client layer (`api/client.py`): transport and request/reply lifecycle.

This keeps helpers as a pure convenience layer with zero transport coupling.

### 5.2 Builder rules

- Builders must be deterministic and side-effect free.
- Builders return generated `ActionRequest` only.
- Builders must not call `NiriClient` directly.
- Builders should be thin wrappers over generated variants.

### 5.3 Naming and stability policy

- Use snake_case function names matching user intent, not generated class names.
- Prefer domain names that map to existing Niri actions (`move_workspace_to_monitor`, not abbreviations).
- If generated type names evolve, preserve helper function names and update internals.

### 5.4 Optional typed presets

If downstream usage shows repeated multi-action patterns, add `presets.py` that returns lists/tuples of `ActionRequest`.

Example:

- `prepare_workspace(name: str, output: str | None = None) -> tuple[ActionRequest, ...]`

This should remain optional and only be added once real use-cases exist.

## 6. Metadata Compatibility Surface Architecture

### 6.1 Metadata model

Define explicit models so callers no longer parse module constants.

Proposed model set:

- `ProtocolMetadata`
  - `upstream_crate: str`
  - `upstream_version: str`
  - `generator_version: str`
  - `ir_version: str`
  - `ir_hash: str`
  - `schema_hashes: dict[SchemaKind, str]`
- `SchemaKind` enum
  - `request`, `reply`, `event`, `action`
- `CompatibilityResult`
  - `ok: bool`
  - `reason: str`
  - `details: dict[str, str]`
- `CompatibilityReport`
  - aggregate of multiple checks and metadata snapshot

### 6.2 Source of truth

`compat/metadata.py` should read directly from `types.generated._metadata` constants and convert into typed models. No duplicated constants.

### 6.3 Comparison semantics

- `upstream_version` checks should parse semantic-ish version strings where possible.
- If version parsing is ambiguous, fall back to explicit failure with clear reason.
- Hash checks (`ir_hash`, `schema_hashes`) should be strict equality.

### 6.4 Intended consumers

- Downstream libraries can fail fast during startup if incompatible.
- Diagnostic commands can print clear compatibility reports.
- CI checks can gate upgrades by comparing expected schema hashes.

## 7. Backward Compatibility Strategy

1. Keep all existing generated exports untouched.
2. Keep `niri_pypc.types.generated` wildcard behavior unchanged.
3. Add new imports in top-level `src/niri_pypc/__init__.py` without removing old ones.
4. Do not deprecate direct generated imports initially.
5. Introduce documentation preference, not hard API pressure, in first release.

Potential later deprecation path:

- After one or more minor releases, deprecate only highly brittle direct imports if needed.
- Keep generated modules public for advanced users and protocol-level integrations.

## 8. Implementation Plan (Phased)

### Phase 1: Action helper MVP

- Create `actions/builders.py` with a focused set of 8-12 high-value action builders.
- Add `actions/__init__.py` re-exports.
- Add docstrings with generated type mapping notes.
- Export `actions` from package root.

Exit criteria:

- Typical workspace/window orchestration actions are constructible without touching generated classes.

### Phase 2: Metadata compatibility MVP

- Create `compat/models.py` and `compat/metadata.py`.
- Implement `get_protocol_metadata()`.
- Add base check functions in `compat/checks.py` for IR hash and schema hash equality.
- Export `compat` from package root.

Exit criteria:

- Downstream callers can get typed metadata and run deterministic hash checks.

### Phase 3: Expanded checks and reporting

- Add version threshold checks and structured report builder.
- Add concise `format_compat_report()` helper for CLI/tooling use.
- Add error classes in `errors.py` only if required by real workflows.

Exit criteria:

- Compatibility output is useful in automated checks and human diagnostics.

### Phase 4: Adoption and hardening

- Update examples to use helper builders.
- Add integration-style tests showing helpers + `NiriClient.request(...)` contract compatibility.
- Collect downstream feedback and fill helper surface gaps.

Exit criteria:

- At least one downstream integration path can stop importing generated action classes directly.

## 9. Testing Strategy

### 9.1 Unit tests for action builders

Add tests that validate each builder returns the expected nested generated structure.

Suggested file:

- `tests/actions/test_builders.py`

Test patterns:

- Type assertion: result is `ActionRequest`.
- Variant assertion: payload root is expected generated action variant.
- Field mapping assertion: inputs correctly mapped to generated payload fields.

### 9.2 Unit tests for metadata models and checks

Suggested files:

- `tests/compat/test_metadata.py`
- `tests/compat/test_checks.py`

Test patterns:

- `get_protocol_metadata()` mirrors constants from `_metadata.py`.
- Known-good and known-bad hash checks.
- Version-check parsing behavior with valid and invalid version inputs.

### 9.3 Regression tests for public imports

Add tests that ensure imports remain stable.

Suggested file:

- `tests/test_public_api_surface.py`

Assertions:

- Existing generated imports still work.
- New `actions` and `compat` surfaces import cleanly.

## 10. Documentation and Migration Guidance

Update documentation with three goals:

1. Show old and new ways side-by-side.
2. Recommend helpers for common use-cases.
3. Explain when direct generated imports are still appropriate.

Suggested docs changes:

- README section: "Action Builders"
- README section: "Protocol Metadata and Compatibility"
- API reference stubs for `niri_pypc.actions` and `niri_pypc.compat`

Migration example style:

- Before: manual `ActionRequest(payload=SomeAction(...))`
- After: `actions.some_action(...)`

## 11. Risks and Mitigations

Risk: helper API drifts from generated model capabilities.

- Mitigation: keep helpers thin; map directly to generated variants; add tests per helper.

Risk: helpers become overly broad and hard to maintain.

- Mitigation: start with minimal high-value set; require downstream use-case evidence for additions.

Risk: compatibility checks create false confidence about runtime behavior.

- Mitigation: document that metadata compatibility is necessary but not sufficient; runtime environment checks still matter.

Risk: version parsing edge-cases due to non-standard version strings.

- Mitigation: make parsing strict; return explicit non-ok result with reason when parsing is ambiguous.

## 12. Open Questions

1. Should `actions` return `ActionRequest` objects or raw `Action` payloads plus a separate wrapper helper?
2. Do we want a dedicated exception type for compatibility failures in this library, or keep checks as pure return-value APIs?
3. Should schema compatibility checks support partial-match policies (for example only `action` + `request`) or always evaluate all schema kinds?
4. Should we include convenience `client.request_action(...)` overloads now, or defer to keep transport API minimal?

## 13. Suggested Initial Patch Set

PR 1: Action helper foundation

- Add `src/niri_pypc/actions/{__init__.py,builders.py}`.
- Add tests for action builders.
- Add minimal README usage snippet.

PR 2: Compatibility metadata foundation

- Add `src/niri_pypc/compat/{__init__.py,models.py,metadata.py,checks.py}`.
- Add tests for metadata extraction and checks.
- Add README compatibility snippet.

PR 3: Surface integration

- Re-export new modules from package root.
- Add public API surface regression tests.
- Final docs cleanup and changelog note.

This sequence keeps risk low, allows quick downstream validation, and preserves full backward compatibility while introducing a significantly better developer-facing API.
