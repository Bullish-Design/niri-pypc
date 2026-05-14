from __future__ import annotations

from functools import cache
from typing import Any, ClassVar, Literal, TypeVar

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


RootT = TypeVar("RootT", bound=ProtocolModel)


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
        root = self.root
        if isinstance(root, UnknownEvent):
            return {root.variant_name: root.raw_payload}

        if not isinstance(root, ProtocolVariant):
            raise TypeError(f"Cannot encode non-variant: {type(root).__name__}")

        wire_name = root.__niri_wire_name__
        kind = root.__niri_variant_kind__

        if kind == "unit":
            return wire_name
        if kind == "newtype":
            if not hasattr(root, "payload"):
                raise TypeError(
                    f"Newtype variant {type(root).__name__} is missing required payload field",
                )
            return {wire_name: root.payload}
        if kind == "struct":
            return {wire_name: root.model_dump(mode="json")}

        raise ValueError(f"Unknown variant kind: {kind}")

    @classmethod
    @cache
    def _variant_map(cls) -> dict[str, type[ProtocolVariant]]:
        return {variant.__niri_wire_name__: variant for variant in cls.__niri_variants__}
