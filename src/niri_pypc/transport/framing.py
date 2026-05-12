"""Minimal framing utilities."""

from __future__ import annotations


def append_newline(payload: bytes) -> bytes:
    return payload + b"\n"
