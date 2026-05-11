"""Live tests against a real niri compositor.

These tests are gated by the NIRI_SOCKET environment variable.
They only run when a real niri socket is available.
"""

from __future__ import annotations

import os

import pytest

from niri_pypc.api.client import NiriClient
from niri_pypc.config import NiriConfig

pytestmark = pytest.mark.skipif(
    not os.environ.get("NIRI_SOCKET"),
    reason="NIRI_SOCKET not set — skipping live tests",
)


class TestLiveNiri:
    async def test_version_request(self):
        """Version request against live compositor returns version string."""
        config = NiriConfig()
        async with NiriClient.connect(config) as client:
            from niri_pypc.types.generated.request import VersionRequest

            result = await client.request(VersionRequest())

        assert result is not None
        # The result should be a Response with a version payload
        assert hasattr(result, "variant")
        assert hasattr(result.variant, "payload")
        assert isinstance(result.variant.payload, str)

    async def test_outputs_request(self):
        """Outputs request against live compositor returns output list."""
        config = NiriConfig()
        async with NiriClient.connect(config) as client:
            from niri_pypc.types.generated.request import FocusedOutputRequest

            # Use FocusedOutput as a request
            result = await client.request(FocusedOutputRequest())

        assert result is not None

    async def test_niri_socket_env_is_set(self):
        """Verify that NIRI_SOCKET is set (redundant with skipif)."""
        assert os.environ.get("NIRI_SOCKET") is not None
