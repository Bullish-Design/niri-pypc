"""Contract tests for the metadata-driven codec."""

from __future__ import annotations

from typing import Any

import pytest

from niri_pypc.errors import DecodeError, EncodeError
from niri_pypc.types.base import ExternallyTaggedEnum, ProtocolModel, ProtocolVariant, UnknownEvent
from niri_pypc.types.codec import decode_externally_tagged, encode_externally_tagged


class Ping(ProtocolVariant):
    __niri_wire_name__ = "Ping"
    __niri_variant_kind__ = "unit"


class Echo(ProtocolVariant):
    __niri_wire_name__ = "Echo"
    __niri_variant_kind__ = "newtype"

    payload: str


class Full(ProtocolVariant):
    __niri_wire_name__ = "Full"
    __niri_variant_kind__ = "struct"

    name: str
    count: int


class ZeroStruct(ProtocolVariant):
    __niri_wire_name__ = "ZeroStruct"
    __niri_variant_kind__ = "struct"


class UnknownTestVariant(ProtocolModel):
    variant_name: str
    raw_payload: Any


UnknownTestVariant.model_rebuild()


VARIANTS = {
    "Ping": Ping,
    "Echo": Echo,
    "Full": Full,
    "ZeroStruct": ZeroStruct,
}


class TestCodecContract:
    def test_unit_variant_encodes_to_string(self):
        result = encode_externally_tagged(Ping())
        assert result == "Ping"

    def test_newtype_variant_encodes_to_tagged_scalar(self):
        result = encode_externally_tagged(Echo(payload="hello"))
        assert result == {"Echo": "hello"}

    def test_struct_variant_encodes_to_tagged_object(self):
        result = encode_externally_tagged(Full(name="foo", count=7))
        assert result == {"Full": {"name": "foo", "count": 7}}

    def test_zero_field_struct_encodes_to_tagged_empty_object(self):
        result = encode_externally_tagged(ZeroStruct())
        assert result == {"ZeroStruct": {}}

    def test_unit_variant_decodes_from_string(self):
        result = decode_externally_tagged("Ping", VARIANTS)
        assert isinstance(result, Ping)

    def test_newtype_variant_decodes_from_tagged_scalar(self):
        result = decode_externally_tagged({"Echo": "world"}, VARIANTS)
        assert isinstance(result, Echo)
        assert result.payload == "world"

    def test_struct_variant_decodes_from_tagged_object(self):
        result = decode_externally_tagged({"Full": {"name": "bar", "count": 3}}, VARIANTS)
        assert isinstance(result, Full)
        assert result.name == "bar"
        assert result.count == 3

    def test_zero_field_struct_decodes_from_tagged_empty_object(self):
        result = decode_externally_tagged({"ZeroStruct": {}}, VARIANTS)
        assert isinstance(result, ZeroStruct)

    def test_struct_variant_rejects_string_form(self):
        with pytest.raises(DecodeError, match="requires object payload"):
            decode_externally_tagged("Full", VARIANTS)

    def test_unit_variant_rejects_object_form_with_nonempty_payload(self):
        with pytest.raises(DecodeError, match="must use string form"):
            decode_externally_tagged({"Ping": {"extra": "data"}}, VARIANTS)

    def test_unknown_event_returns_unknown_sentinel(self):
        result = decode_externally_tagged(
            {"NewFutureVariant": {"some": "data"}},
            VARIANTS,
            unknown_variant_model=UnknownTestVariant,
        )
        assert isinstance(result, UnknownTestVariant)
        assert result.variant_name == "NewFutureVariant"

    def test_unknown_unit_event_returns_unknown_sentinel(self):
        result = decode_externally_tagged(
            "NewUnitVariant",
            VARIANTS,
            unknown_variant_model=UnknownTestVariant,
        )
        assert isinstance(result, UnknownTestVariant)
        assert result.variant_name == "NewUnitVariant"

    def test_unknown_variant_without_sentinel_raises(self):
        with pytest.raises(DecodeError, match="Unknown variant"):
            decode_externally_tagged({"Bogus": {}}, VARIANTS)

    def test_unknown_unit_variant_without_sentinel_raises(self):
        with pytest.raises(DecodeError, match="Unknown unit variant"):
            decode_externally_tagged("Bogus", VARIANTS)

    def test_empty_dict_raises(self):
        with pytest.raises(DecodeError, match="Expected exactly one"):
            decode_externally_tagged({}, VARIANTS)

    def test_multi_key_dict_raises(self):
        with pytest.raises(DecodeError, match="Expected exactly one"):
            decode_externally_tagged({"Ping": {}, "Echo": "x"}, VARIANTS)

    def test_non_dict_non_string_raises(self):
        with pytest.raises(DecodeError, match="Expected externally-tagged"):
            decode_externally_tagged(42, VARIANTS)

    def test_encode_non_protocol_variant_raises(self):
        with pytest.raises(EncodeError, match="Cannot externally-tag non-variant"):
            encode_externally_tagged(ProtocolModel())
