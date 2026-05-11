"""Edge case tests for generated type models."""

from __future__ import annotations

from niri_pypc.errors import DecodeError
from niri_pypc.types.generated.request import Request


class TestEdgeCases:
    def test_none_request_raises(self):
        """None input raises DecodeError."""
        try:
            Request.model_validate(None)
            assert False, "Expected error"
        except DecodeError:
            pass

    def test_empty_dict_request_raises(self):
        """Empty dict input raises DecodeError."""
        try:
            Request.model_validate({})
            assert False, "Expected error"
        except DecodeError:
            pass

    def test_multi_key_dict_raises(self):
        """Dict with multiple keys raises DecodeError."""
        try:
            Request.model_validate({"Version": None, "EventStream": None})
            assert False, "Expected error"
        except DecodeError:
            pass
