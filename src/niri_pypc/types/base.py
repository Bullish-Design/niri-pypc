from __future__ import annotations

from functools import cache
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, RootModel, model_serializer, model_validator

from niri_pypc.errors import DecodeError

type VariantKind = Literal["unit", "newtype", "struct"]


class ProtocolModel(BaseModel):
    """Base for all generated protocol models."""

    model_config = ConfigDict(
        frozen=True,
        strict=False,
        extra="forbid",
        populate_by_name=True,
    )


class ProtocolVariant(ProtocolModel):
    """Base for generated externally-tagged enum variants."""

    __niri_wire_name__: ClassVar[str]
    __niri_variant_kind__: ClassVar[VariantKind]


class UnknownEvent(ProtocolModel):
    """Forward-compatible unknown event sentinel."""

    variant_name: str
    raw_payload: Any


class ExternallyTaggedEnum[RootT: ProtocolModel](RootModel[RootT]):
    """Generic RootModel for externally-tagged enums."""

    __niri_variants__: ClassVar[tuple[type[ProtocolVariant], ...]]
    __niri_unknown_variant_model__: ClassVar[type[ProtocolModel] | None] = None

    @model_validator(mode="before")
    @classmethod
    def _decode_root(cls, data: Any) -> Any:
        if isinstance(data, cls):
            return data

        # Direct construction: ExternallyTaggedEnum(root=Variant())
        if isinstance(data, dict) and "root" in data:
            root_val = data["root"]
            if isinstance(root_val, ProtocolModel):
                return data
            raise DecodeError(
                "root value must be a ProtocolModel instance",
                operation="ExternallyTaggedEnum._decode_root",
            )

        if isinstance(data, ProtocolModel):
            return data

        # Raw wire data: decode inline using metadata
        from niri_pypc.types.codec import decode_externally_tagged

        return decode_externally_tagged(
            data,
            cls._variant_map(),
            unknown_variant_model=cls.__niri_unknown_variant_model__,
        )

    @model_serializer(mode="plain")
    def _encode_root(self) -> Any:
        from niri_pypc.types.codec import encode_externally_tagged

        return encode_externally_tagged(self.root)

    @classmethod
    @cache
    def _variant_map(cls) -> dict[str, type[ProtocolVariant]]:
        return {variant.__niri_wire_name__: variant for variant in cls.__niri_variants__}
