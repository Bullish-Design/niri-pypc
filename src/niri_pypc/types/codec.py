"""Externally-tagged enum encode/decode primitives."""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from niri_pypc.errors import DecodeError, EncodeError, RemoteError


def decode_externally_tagged(
    data: Any,
    variants: dict[str, type[BaseModel]],
    *,
    unknown_sentinel: type[BaseModel] | None = None,
) -> BaseModel:
    """Decode an externally-tagged serde enum value."""
    if isinstance(data, str):
        cls = variants.get(data)
        if cls is not None:
            return cls()
        if unknown_sentinel is not None:
            return unknown_sentinel(variant_name=data, raw_payload=data)
        raise DecodeError(
            f"Unknown unit variant: {data}",
            operation="decode_externally_tagged",
            raw_payload=data,
        )

    if isinstance(data, dict):
        if len(data) != 1:
            raise DecodeError(
                f"Expected exactly one key in externally-tagged dict, got {len(data)}",
                operation="decode_externally_tagged",
                raw_payload=str(data),
            )

        variant_name = next(iter(data.keys()))
        if not isinstance(variant_name, str):
            raise DecodeError(
                f"Expected string key in externally-tagged dict, got {type(variant_name).__name__}",
                operation="decode_externally_tagged",
                raw_payload=str(data),
            )

        payload = data[variant_name]
        cls = variants.get(variant_name)

        if cls is None:
            if unknown_sentinel is not None:
                return unknown_sentinel(variant_name=variant_name, raw_payload=payload)
            raise DecodeError(
                f"Unknown variant: {variant_name}",
                operation="decode_externally_tagged",
                raw_payload=str(data),
            )

        fields = cls.model_fields
        if not fields:
            return cls()
        if list(fields.keys()) == ["payload"]:
            return cls(payload=payload)
        return cls.model_validate(payload)

    raise DecodeError(
        f"Expected string or dict, got {type(data).__name__}",
        operation="decode_externally_tagged",
        raw_payload=str(data),
    )


def encode_externally_tagged(
    variant: BaseModel,
    variant_names: dict[type[BaseModel], str],
) -> Any:
    """Encode a variant model instance into externally-tagged wire format."""
    cls = type(variant)
    wire_name = variant_names.get(cls)

    if wire_name is None:
        raise EncodeError(
            f"Unknown variant class: {cls.__name__}",
            operation="encode_externally_tagged",
        )

    model_fields = cls.model_fields
    if not model_fields:
        return wire_name

    if list(model_fields.keys()) == ["payload"]:
        payload = cast(Any, variant).payload
        if isinstance(payload, BaseModel):
            return {wire_name: payload.model_dump(mode="json", by_alias=True)}
        return {wire_name: payload}

    return {wire_name: variant.model_dump(mode="json", by_alias=True)}


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
