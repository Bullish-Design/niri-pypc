"""Live test configuration - skip tests when NIRI_SOCKET is not set."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("NIRI_SOCKET"),
    reason="NIRI_SOCKET not set — skipping live tests",
)
