# Progress

## Tasks
- [x] Read project review and identify high-priority fixes from section 10.
- [x] Fix README API examples (`.variant.payload` -> `.payload`).
- [x] Remove dual encode implementation by delegating `ExternallyTaggedEnum._encode_root` to codec.
- [x] Replace silent schema fallback in `tools/normalize_ir.py` with explicit error.
- [x] Add regression test for newtype payload model serialization through root-model encode path.
- [x] Implement remaining medium-priority non-test fixes (`API-1`, `API-5`, `A-1`).
- [x] Implement full suite variant roundtrip coverage for request/event/reply variants (`TEST-1`).
- [x] Implement concurrent event stream operation tests (`TEST-2`): concurrent waiters, close-while-waiting, terminal decode wakeup, rapid open/close cycles.
- [x] Run lint/format/targeted test validation and resolve failures.
- [x] Final verification summary and handoff.
