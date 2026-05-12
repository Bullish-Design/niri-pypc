"""Externally-tagged enum encode/decode primitives - metadata-driven."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from niri_pypc.errors import DecodeError, EncodeError, RemoteError
from niri_pypc.types.base import ProtocolModel, ProtocolVariant, UnknownEvent


def _dump_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def decode_externally_tagged(
    data: Any,
    variants: dict[str, type[ProtocolVariant]],
    *,
    unknown_variant_model: type[ProtocolModel] | None = None,
) -> ProtocolModel:
    """Decode an externally-tagged serde enum value.

    Uses explicit variant metadata (__niri_wire_name__, __niri_variant_kind__)
    rather than field-shape heuristics.
    """
    if isinstance(data, str):
        variant_cls = variants.get(data)
        if variant_cls is None:
            if unknown_variant_model is not None:
                return unknown_variant_model(variant_name=data, raw_payload=data)
            raise DecodeError(
                f"Unknown unit variant: {data}",
                operation="decode_externally_tagged",
                raw_payload=str(data),
            )

        if variant_cls.__niri_variant_kind__ != "unit":
            raise DecodeError(
                f"Variant {data} requires object payload, got string unit form",
                operation="decode_externally_tagged",
                raw_payload=str(data),
            )

        return variant_cls()

    if not isinstance(data, dict):
        raise DecodeError(
            f"Expected externally-tagged string or dict, got {type(data).__name__}",
            operation="decode_externally_tagged",
            raw_payload=str(data),
        )

    if len(data) != 1:
        raise DecodeError(
            f"Expected exactly one externally-tagged key, got {len(data)}",
            operation="decode_externally_tagged",
            raw_payload=str(data),
        )

    variant_name, payload = next(iter(data.items()))
    if not isinstance(variant_name, str):
        raise DecodeError(
            f"Expected string variant name, got {type(variant_name).__name__}",
            operation="decode_externally_tagged",
            raw_payload=str(data),
        )

    variant_cls = variants.get(variant_name)
    if variant_cls is None:
        if unknown_variant_model is not None:
            return unknown_variant_model(variant_name=variant_name, raw_payload=payload)
        raise DecodeError(
            f"Unknown variant: {variant_name}",
            operation="decode_externally_tagged",
            raw_payload=str(data),
        )

    kind = variant_cls.__niri_variant_kind__

    if kind == "unit":
        if payload != {}:
            raise DecodeError(
                f"Unit variant {variant_name} must use string form, not payload form",
                operation="decode_externally_tagged",
                raw_payload=str(data),
            )
        return variant_cls()

    if kind == "newtype":
        return variant_cls(payload=payload)

    if kind == "struct":
        if not isinstance(payload, dict):
            raise DecodeError(
                f"Struct variant {variant_name} requires object payload, got {type(payload).__name__}",
                operation="decode_externally_tagged",
                raw_payload=str(data),
            )
        return variant_cls.model_validate(payload)

    raise DecodeError(
        f"Unsupported variant kind: {kind}",
        operation="decode_externally_tagged",
        raw_payload=str(data),
    )


def encode_externally_tagged(value: ProtocolModel) -> Any:
    """Encode a variant model instance into externally-tagged wire format.

    Uses explicit variant metadata rather than field-shape heuristics.
    """
    if isinstance(value, UnknownEvent):
        return {value.variant_name: value.raw_payload}

    if not isinstance(value, ProtocolVariant):
        raise EncodeError(
            f"Cannot externally-tag non-variant type: {type(value).__name__}",
            operation="encode_externally_tagged",
        )

    wire_name = value.__niri_wire_name__
    kind = value.__niri_variant_kind__

    if kind == "unit":
        return wire_name

    if kind == "newtype":
        return {wire_name: _dump_value(value.payload)}

    if kind == "struct":
        return {wire_name: value.model_dump(mode="json")}

    raise EncodeError(
        f"Unsupported variant kind: {kind}",
        operation="encode_externally_tagged",
    )


def unwrap_reply(reply: BaseModel) -> Any:
    """Unwrap a niri Reply envelope."""
    variant = getattr(reply, "variant", None)
    if variant is None:
        raise DecodeError(
            "Reply missing variant field",
            operation="unwrap_reply",
        )

    from niri_pypc.types.generated.reply import ErrReply, OkReply

    if isinstance(variant, OkReply):
        return getattr(variant, "payload", variant)
    if isinstance(variant, ErrReply):
        msg = getattr(variant, "payload", str(variant))
        raise RemoteError(
            f"Compositor error: {msg}",
            operation="unwrap_reply",
            remote_message=str(msg),
        )

    raise DecodeError(
        f"Unexpected reply variant: {type(variant).__name__}",
        operation="unwrap_reply",
    )
