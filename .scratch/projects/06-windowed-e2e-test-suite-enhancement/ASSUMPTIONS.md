# Assumptions

- This project is planning-only and does not yet modify runtime test code.
- `niri-pypc` tests should avoid connecting to a developer's real compositor session by default.
- Nested/windowed niri execution is the preferred integration-testing path for realistic local verification.
- Niri configuration for E2E tests should be explicit, checked-in, and readable by developers.
- Multiple fixture configurations are needed to validate scenario-specific behavior (minimal, multi-output, and stress-like setups).
- Environment-dependent commands (when later implementing this plan) must run via `devenv shell -- ...`.
