"""Tests for generated _metadata.py provenance."""

from __future__ import annotations

import pytest

from niri_pypc.types.generated._metadata import (
    GENERATOR_VERSION,
    IR_HASH,
    IR_VERSION,
    SCHEMA_HASHES,
    UPSTREAM_CRATE,
    UPSTREAM_VERSION,
)

pytestmark = pytest.mark.contract


class TestMetadata:
    def test_upstream_crate(self):
        assert UPSTREAM_CRATE == "niri-ipc"

    def test_upstream_version(self):
        assert UPSTREAM_VERSION == "25.11"

    def test_generator_version(self):
        assert GENERATOR_VERSION == "1"

    def test_ir_version(self):
        assert IR_VERSION == "1"

    def test_ir_hash_present(self):
        assert IR_HASH.startswith("sha256:")

    def test_schema_hashes_present(self):
        assert "request" in SCHEMA_HASHES
        assert "reply" in SCHEMA_HASHES
        assert "event" in SCHEMA_HASHES
        assert "action" in SCHEMA_HASHES

    def test_schema_hashes_format(self):
        for name, hash_val in SCHEMA_HASHES.items():
            assert hash_val.startswith("sha256:"), f"{name} hash should start with sha256:"
