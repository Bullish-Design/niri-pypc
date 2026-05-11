"""Tests for the framing module."""

from __future__ import annotations

import pytest

from niri_pypc.errors import DecodeError
from niri_pypc.transport.framing import decode_frame, encode_frame


class TestEncodeFrame:
    def test_encodes_string(self):
        result = encode_frame("hello")
        assert result == b'"hello"\n'

    def test_encodes_dict(self):
        result = encode_frame({"key": "value"})
        assert result == b'{"key":"value"}\n'

    def test_encodes_list(self):
        result = encode_frame([1, 2, 3])
        assert result == b"[1,2,3]\n"

    def test_encodes_none(self):
        result = encode_frame(None)
        assert result == b"null\n"

    def test_encodes_int(self):
        result = encode_frame(42)
        assert result == b"42\n"

    def test_compact_separators(self):
        """Verify compact JSON separators (no spaces)."""
        result = encode_frame({"a": 1, "b": 2})
        assert b" " not in result

    def test_always_newline_terminated(self):
        result = encode_frame("x")
        assert result.endswith(b"\n")


class TestDecodeFrame:
    def test_decodes_string(self):
        assert decode_frame(b'"hello"') == "hello"

    def test_decodes_dict(self):
        assert decode_frame(b'{"key":"value"}') == {"key": "value"}

    def test_decodes_list(self):
        assert decode_frame(b"[1,2,3]") == [1, 2, 3]

    def test_decodes_null(self):
        assert decode_frame(b"null") is None

    def test_decodes_int(self):
        assert decode_frame(b"42") == 42

    def test_decodes_float(self):
        assert decode_frame(b"3.14") == 3.14

    def test_decodes_bool(self):
        assert decode_frame(b"true") is True
        assert decode_frame(b"false") is False

    def test_invalid_json_raises_decode_error(self):
        with pytest.raises(DecodeError, match="Failed to decode frame"):
            decode_frame(b"{invalid}")

    def test_empty_bytes_raises_decode_error(self):
        with pytest.raises(DecodeError):
            decode_frame(b"")

    def test_partial_json_raises_decode_error(self):
        with pytest.raises(DecodeError):
            decode_frame(b'{"key"')

    def test_invalid_unicode_raises_decode_error(self):
        with pytest.raises(DecodeError):
            decode_frame(b"\xff\xfe\x00\x01")


class TestRoundtrip:
    def test_string_roundtrip(self):
        assert decode_frame(encode_frame("hello")) == "hello"

    def test_dict_roundtrip(self):
        original = {"a": 1, "b": [2, 3], "c": {"d": "e"}}
        assert decode_frame(encode_frame(original)) == original

    def test_list_roundtrip(self):
        original = [1, "two", {"three": 3}]
        assert decode_frame(encode_frame(original)) == original

    def test_none_roundtrip(self):
        assert decode_frame(encode_frame(None)) is None

    def test_nested_structure_roundtrip(self):
        original = {"level1": {"level2": {"level3": [1, 2, 3]}}}
        assert decode_frame(encode_frame(original)) == original
