# ASSUMPTIONS

1. The authoritative reference for execution order and per-step verification is `NIRI_PYPC_IMPLEMENTATION_GUIDE.md` in the `01-niri-pypc-final-concept` project directory.
2. All environment-dependent commands use `devenv shell -- ...` as the invocation wrapper.
3. Python 3.13+ is the target runtime; asyncio is the only concurrency model; Unix sockets are the only transport.
4. The package name is `niri-pypc`; the import root is `niri_pypc`.
5. Generated code goes in `src/niri_pypc/types/generated/` and is never manually edited.
6. Manual code lives everywhere else in the package.
7. The upstream pin is `niri-ipc = "25.11"` with feature `json-schema`.
8. `NIRI_SOCKET` environment variable or explicit `NiriConfig.socket_path` are the only two socket discovery mechanisms.
9. Tests always provide explicit temporary socket paths via `NiriConfig` — never rely on `NIRI_SOCKET` being set.
10. The implementation is done when the end-to-end verification checklist (Step 24) passes completely.
11. No code generation or project scaffolding currently exists in the repository — this is a greenfield implementation.
