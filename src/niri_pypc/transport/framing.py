"""Newline-delimited JSON frame encoding and decoding."""

from __future__ import annotations

import json
from typing import Any

from niri_pypc.errors import DecodeError, EncodeError


def encode_frame(data: Any) -> bytes:
    """Serialize data to a newline-terminated JSON frame."""
    try:
        return json.dumps(data, separators=(",", ":")).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise EncodeError(
            f"Failed to encode frame: {exc}",
            operation="encode_frame",
            cause=exc,
        ) from exc


def decode_frame(raw: bytes) -> Any:
    """Deserialize a raw frame into a Python object."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DecodeError(
            f"Failed to decode frame: {exc}",
            operation="decode_frame",
            raw_payload=raw.decode("utf-8", errors="replace"),
            cause=exc,
        ) from exc
