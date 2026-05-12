"""Edge case tests for generated type models."""

from __future__ import annotations

import pytest

from niri_pypc.errors import DecodeError
from niri_pypc.types.generated.request import Request

pytestmark = pytest.mark.contract


class TestEdgeCases:
    def test_none_request_raises(self):
        """None input raises DecodeError."""
        with pytest.raises(DecodeError):
            Request.model_validate(None)

    def test_empty_dict_request_raises(self):
        """Empty dict input raises DecodeError."""
        with pytest.raises(DecodeError):
            Request.model_validate({})

    def test_multi_key_dict_raises(self):
        """Dict with multiple keys raises DecodeError."""
        with pytest.raises(DecodeError):
            Request.model_validate({"Version": None, "EventStream": None})
