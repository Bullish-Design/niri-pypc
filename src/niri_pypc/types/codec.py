"""Externally-tagged enum encode/decode primitives."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from niri_pypc.errors import DecodeError, RemoteError


def decode_externally_tagged(
    data: Any,
    variants: dict[str, type[BaseModel]],
    *,
    unknown_sentinel: type[BaseModel] | None = None,
) -> BaseModel:
    """Decode an externally-tagged serde enum value.

    Args:
        data: Raw JSON-parsed value. Either a dict with one key (variant name)
              and the payload as value, or a string (unit variant name).
        variants: Wire-name to variant model class mapping.
        unknown_sentinel: If provided and variant is unknown, construct this
                          sentinel model with variant_name and raw_payload.

    Returns:
        An instance of the matched variant model.

    Raises:
        DecodeError: If data shape is invalid or variant is unknown.
    """
    if isinstance(data, str):
        # Unit variant: just the variant name as a string
        cls = variants.get(data)
        if cls is not None:
            return cls()
        if unknown_sentinel is not None:
            return unknown_sentinel(variant_name=data, raw_payload=data)
        raise DecodeError(
            f"Unknown unit variant: {data}",
            operation="decode_externally_tagged",
            raw_payload=data[:1024],
        )

    if isinstance(data, dict):
        if len(data) != 1:
            raise DecodeError(
                f"Expected exactly one key in externally-tagged dict, got {len(data)}",
                operation="decode_externally_tagged",
                raw_payload=str(data)[:1024],
            )

        variant_name = next(iter(data.keys()))
        payload = data[variant_name]
        cls = variants.get(variant_name)

        if cls is None:
            if unknown_sentinel is not None:
                return unknown_sentinel(variant_name=variant_name, raw_payload=payload)
            raise DecodeError(
                f"Unknown variant: {variant_name}",
                operation="decode_externally_tagged",
                raw_payload=str(data)[:1024],
            )

        # Determine variant kind from field structure
        fields = cls.model_fields
        if not fields:
            return cls()
        if list(fields.keys()) == ["payload"]:
            return cls(payload=payload)
        return cls.model_validate(payload)

    raise DecodeError(
        f"Expected string or dict, got {type(data).__name__}",
        operation="decode_externally_tagged",
        raw_payload=str(data)[:1024],
    )


def encode_externally_tagged(
    variant: BaseModel,
    variant_names: dict[type[BaseModel], str],
) -> Any:
    """Encode a variant model instance into externally-tagged wire format.

    Args:
        variant: The variant model instance.
        variant_names: Model class to wire-name mapping.

    Returns:
        For unit variants: the wire name as a string.
        For newtype/struct variants: {"WireName": payload_dict}.
    """
    cls = type(variant)
    wire_name = variant_names.get(cls)

    if wire_name is None:
        raise DecodeError(
            f"Unknown variant class: {cls.__name__}",
            operation="encode_externally_tagged",
        )

    # Check if it's a unit variant (no fields)
    model_fields = cls.model_fields
    if not model_fields:
        return wire_name

    # Check if it's a newtype variant (single 'payload' field)
    if list(model_fields.keys()) == ["payload"]:
        payload = variant.payload
        if isinstance(payload, BaseModel):
            return {wire_name: payload.model_dump(mode="json", by_alias=True)}
        return {wire_name: payload}

    # Struct variant: serialize all fields
    return {wire_name: variant.model_dump(mode="json", by_alias=True)}


def unwrap_reply(reply: BaseModel) -> Any:
    """Unwrap a niri Reply envelope.

    Args:
        reply: A Reply model instance.

    Returns:
        The Ok payload value.

    Raises:
        RemoteError: If the response is an Err.
        DecodeError: If unexpected shape.
    """
    variant = getattr(reply, "variant", None)
    if variant is None:
        raise DecodeError(
            "Reply missing variant field",
            operation="unwrap_reply",
        )

    cls_name = type(variant).__name__

    if cls_name.startswith("Ok"):
        return getattr(variant, "payload", variant)
    if cls_name.startswith("Err"):
        msg = getattr(variant, "payload", str(variant))
        raise RemoteError(
            f"Compositor error: {msg}",
            operation="unwrap_reply",
            remote_message=str(msg),
        )

    raise DecodeError(
        f"Unexpected reply variant: {cls_name}",
        operation="unwrap_reply",
    )
