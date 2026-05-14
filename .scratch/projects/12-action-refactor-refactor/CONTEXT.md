# CONTEXT

- Session started; mandatory rules and implementation guide read.
- User reported prior command impacted visible/nested environment.
- Test policy tightened in repo docs to enforce safer default:
  - `NIRI_PYPC_NESTED_VISIBLE=0 devenv shell -- pytest -m "not nested and not visible_demo and not smoke"`
- Next: continue guide implementation using the stricter safe default unless user explicitly requests nested/visible tests.
