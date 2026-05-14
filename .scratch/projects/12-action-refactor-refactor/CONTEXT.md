# CONTEXT

- Phase 3 complete: `NiriClient.create()` is now canonical; `connect()` preserved as deprecated compatibility alias.
- Migrated call sites to `NiriClient.create()` across:
  - runtime API bundle
  - tests (api/integration/live/helpers)
  - README usage snippets
- Added compatibility test ensuring `NiriClient.create()` and `NiriClient.connect()` both construct equivalent clients.
- Validation:
  - `devenv shell -- pytest tests/api/test_client.py tests/api/test_bundle.py -q` ✅
  - `devenv shell -- ruff check src/niri_pypc/api/client.py src/niri_pypc/api/bundle.py tests/api/test_client.py README.md` ✅
  - `devenv shell -- ruff format --check src/niri_pypc/api/client.py src/niri_pypc/api/bundle.py tests/api/test_client.py` ✅
- Next: Phase 4 failure-path coverage expansion.
