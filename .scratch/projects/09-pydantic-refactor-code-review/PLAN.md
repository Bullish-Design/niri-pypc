# Plan

1. Step 1: Release hygiene and package typing baseline
- Implement single-source runtime version logic.
- Add `py.typed` and package metadata/classifiers/urls.
- Add tests for runtime version and typed marker presence.

2. Step 2: Event stream correctness hardening
- Ensure bootstrap failure closes connection and transitions lifecycle.
- Preserve terminal causes for protocol/transport/unexpected reader failures.
- Add regression tests for bootstrap failure and oversized event behavior.

3. Step 3: Config model hardening + lifecycle docs
- Convert `NiriConfig` to validated frozen Pydantic model.
- Keep compatibility behavior for existing callsites while enforcing positive bounds/types.
- Correct lifecycle thread-safety doc wording.

4. Step 4: Public typing improvements
- Narrow event stream return types to event union type.
- Add request->response overloads for `NiriClient.request` (generated or handwritten).

5. Step 5: CI replacement in devenv scripts + dead-code cleanup/docs alignment
- Add a `devenv` script command that runs lint/type/tests/build/verify-generated checks.
- Address low-severity cleanup from review (`transport/framing.py` usage/removal).
- Update project tracking files to completion.
