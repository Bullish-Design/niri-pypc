"""Tests for the handwritten protocol base layer."""

from __future__ import annotations

import pytest
from pydantic_core import PydanticSerializationError

from niri_pypc.types.base import ExternallyTaggedEnum, ProtocolVariant


class Payload(ProtocolVariant):
    __niri_wire_name__ = "Payload"
    __niri_variant_kind__ = "struct"

    value: str


class Ping(ProtocolVariant):
    __niri_wire_name__ = "Ping"
    __niri_variant_kind__ = "unit"


class Echo(ProtocolVariant):
    __niri_wire_name__ = "Echo"
    __niri_variant_kind__ = "newtype"

    payload: str


class EchoPayload(ProtocolVariant):
    __niri_wire_name__ = "EchoPayload"
    __niri_variant_kind__ = "newtype"

    payload: Payload


class Full(ProtocolVariant):
    __niri_wire_name__ = "Full"
    __niri_variant_kind__ = "struct"

    name: str
    count: int


PingOrEchoOrFull = Ping | Echo | EchoPayload | Full


class Sample(ExternallyTaggedEnum[PingOrEchoOrFull]):
    __niri_variants__ = (Ping, Echo, EchoPayload, Full)


class TestBaseRuntime:
    def test_root_model_round_trip_unit(self):
        value = Sample(root=Ping())
        assert value.model_dump(mode="json") == "Ping"

    def test_root_model_round_trip_newtype(self):
        value = Sample(root=Echo(payload="hi"))
        assert value.model_dump(mode="json") == {"Echo": "hi"}

    def test_root_model_round_trip_newtype_model_payload(self):
        value = Sample(root=EchoPayload(payload=Payload(value="hi")))
        assert value.model_dump(mode="json") == {"EchoPayload": {"value": "hi"}}

    def test_root_model_round_trip_struct(self):
        value = Sample(root=Full(name="test", count=42))
        assert value.model_dump(mode="json") == {"Full": {"name": "test", "count": 42}}

    def test_decode_unit_from_string(self):
        decoded = Sample.model_validate("Ping")
        assert isinstance(decoded.root, Ping)

    def test_decode_newtype_from_tagged_scalar(self):
        decoded = Sample.model_validate({"Echo": "hello"})
        assert isinstance(decoded.root, Echo)
        assert decoded.root.payload == "hello"

    def test_decode_struct_from_tagged_object(self):
        decoded = Sample.model_validate({"Full": {"name": "foo", "count": 7}})
        assert isinstance(decoded.root, Full)
        assert decoded.root.name == "foo"
        assert decoded.root.count == 7

    def test_variant_kind_is_preserved(self):
        assert Ping.__niri_variant_kind__ == "unit"
        assert Echo.__niri_variant_kind__ == "newtype"
        assert Full.__niri_variant_kind__ == "struct"

    def test_variant_wire_name_is_preserved(self):
        assert Ping.__niri_wire_name__ == "Ping"
        assert Echo.__niri_wire_name__ == "Echo"
        assert Full.__niri_wire_name__ == "Full"

    def test_newtype_without_payload_field_raises_type_error(self):
        class BrokenNewtype(ProtocolVariant):
            __niri_wire_name__ = "Broken"
            __niri_variant_kind__ = "newtype"

        class BrokenEnum(ExternallyTaggedEnum[BrokenNewtype]):
            __niri_variants__ = (BrokenNewtype,)

        with pytest.raises(PydanticSerializationError, match="has no attribute 'payload'"):
            BrokenEnum(root=BrokenNewtype()).model_dump(mode="json")
