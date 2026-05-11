"""Newline-delimited JSON frame encoding and decoding."""

from __future__ import annotations

import json
from typing import Any

from niri_pypc.errors import DecodeError


def encode_frame(data: Any) -> bytes:
    """Serialize data to a newline-terminated JSON frame.

    Args:
        data: JSON-serializable value.

    Returns:
        UTF-8 encoded JSON bytes with trailing newline.
    """
    return json.dumps(data, separators=(",", ":")).encode("utf-8") + b"\n"


def decode_frame(raw: bytes) -> Any:
    """Deserialize a raw frame into a Python object.

    Args:
        raw: Raw frame bytes (newline already stripped).

    Returns:
        Parsed JSON value.

    Raises:
        DecodeError: If JSON parsing fails.
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DecodeError(
            f"Failed to decode frame: {exc}",
            operation="decode_frame",
            raw_payload=raw[:1024].decode("utf-8", errors="replace"),
        ) from exc
