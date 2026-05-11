#!/usr/bin/env python3
"""Normalize exported JSON Schema into deterministic generator IR."""

import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path


def load_schema(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def hash_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_ref(ref: str) -> str:
    m = re.match(r"#/\$defs/(.+)", ref)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot resolve ref: {ref}")


def canonical_type(schema: dict, defs: dict) -> str:
    """Convert JSON Schema type notation to canonical IR type string."""
    raw = schema.get("type")
    if isinstance(raw, list):
        if "null" in raw:
            inner = [t for t in raw if t != "null"][0]
            inner_type = _primitive_type(inner)
            return f"option<{inner_type}>" if inner_type else "option<ref:Unknown>"
        return _primitive_type(raw[0])
    if raw:
        return _primitive_type(raw)

    if "$ref" in schema:
        return f"ref:{resolve_ref(schema['$ref'])}"

    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        if non_null:
            inner = canonical_type(non_null[0], defs)
            return f"option<{inner}>"
        return "option<ref:Unknown>"

    if "items" in schema and isinstance(schema["items"], dict):
        inner = canonical_type(schema["items"], defs)
        return f"array<{inner}>"

    if "additionalProperties" in schema and isinstance(schema["additionalProperties"], dict):
        val = canonical_type(schema["additionalProperties"], defs)
        return f"map<string,{val}>"

    if schema.get("properties") and schema["properties"] == {}:
        return "object"

    return "string"


def _primitive_type(t: str) -> str:
    mapping = {
        "string": "string",
        "integer": "integer",
        "number": "float",
        "boolean": "boolean",
        "object": "object",
        "array": "array<ref:Unknown>",
    }
    return mapping.get(t, "string")


def classify_variants(schema: dict, defs: dict, name: str) -> list[dict]:
    """Classify all variants from a oneOf schema."""
    one_of = schema.get("oneOf", [])
    variants = []

    for entry in one_of:
        # Unit variant: {"const": "VariantName", "type": "string"}
        if "const" in entry and entry.get("type") == "string":
            variants.append(
                {
                    "name": entry["const"],
                    "kind": "unit",
                }
            )
            continue

        # Field-variant: {"properties": {"VariantName": <payload>}, "required": ["VariantName"]}
        props = entry.get("properties", {})
        if len(props) == 1:
            var_name = next(iter(props.keys()))
            var_payload = props[var_name]

            # Empty struct: {"VariantName": {"type": "object"}}
            if var_payload.get("type") == "object" and not var_payload.get("properties"):
                variants.append(
                    {
                        "name": var_name,
                        "kind": "struct",
                        "fields": [],
                    }
                )
                continue

            # Newtype variant (ref): {"VariantName": {"$ref": "#/$defs/Type"}}
            if "$ref" in var_payload:
                inner = resolve_ref(var_payload["$ref"])
                variants.append(
                    {
                        "name": var_name,
                        "kind": "newtype",
                        "inner_type": f"ref:{inner}",
                    }
                )
                continue

            # Struct variant (inline fields): {"VariantName": {"properties": {...}}}
            if "properties" in var_payload:
                fields = extract_fields(var_payload, defs)
                variants.append(
                    {
                        "name": var_name,
                        "kind": "struct",
                        "fields": fields,
                    }
                )
                continue

            # Simple value variant (e.g. {"VariantName": {"type": "string"}})
            if "type" in var_payload or "$ref" in var_payload:
                inner = canonical_type(var_payload, defs)
                if inner == "object":
                    variants.append(
                        {
                            "name": var_name,
                            "kind": "struct",
                            "fields": [],
                        }
                    )
                else:
                    variants.append(
                        {
                            "name": var_name,
                            "kind": "newtype",
                            "inner_type": inner,
                        }
                    )
                continue

            # Fallback: treat as struct with extracted fields
            fields = extract_fields(var_payload, defs) if "properties" in var_payload else []
            variants.append(
                {
                    "name": var_name,
                    "kind": "struct",
                    "fields": fields,
                }
            )

    return sorted(variants, key=lambda v: v["name"])


def extract_fields(schema: dict, defs: dict) -> list[dict]:
    """Extract fields from a struct-like schema."""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields = []

    for fname in sorted(props.keys()):
        f_schema = props[fname]
        ftype = canonical_type(f_schema, defs)
        fields.append(
            {
                "name": fname,
                "type": ftype,
                "required": fname in required,
            }
        )

    return fields


def extract_structs(defs: dict) -> list[dict]:
    """Extract struct types from $defs."""
    structs = []
    for name, schema in defs.items():
        if schema.get("type") == "object" and "properties" in schema:
            fields = extract_fields(schema, defs)
            structs.append(
                {
                    "name": name,
                    "kind": "struct",
                    "fields": fields,
                }
            )
    return sorted(structs, key=lambda s: s["name"])


def build_enums(schemas: dict[str, dict], defs: dict) -> list[dict]:
    """Build enum entries from exported schema files."""
    enums = []
    type_config = {
        "request": {"name": "Request"},
        "event": {"name": "Event"},
        "action": {"name": "Action"},
    }

    for key, config in type_config.items():
        schema = schemas[key]
        variants = classify_variants(schema, defs, config["name"])
        enums.append(
            {
                "name": config["name"],
                "kind": "enum",
                "tag_type": "external",
                "variants": variants,
            }
        )

    # Handle Reply (Result<Response, String>)
    reply_schema = schemas["reply"]
    reply_variants = classify_variants(reply_schema, defs, "Reply")
    enums.append(
        {
            "name": "Reply",
            "kind": "enum",
            "tag_type": "external",
            "variants": reply_variants,
        }
    )

    # Extract Response enum from reply's $defs
    response_schema = defs.get("Response")
    if response_schema and "oneOf" in response_schema:
        response_variants = classify_variants(response_schema, defs, "Response")
        enums.append(
            {
                "name": "Response",
                "kind": "enum",
                "tag_type": "external",
                "variants": response_variants,
            }
        )

    return sorted(enums, key=lambda e: e["name"])


def main():
    parser = argparse.ArgumentParser(description="Normalize exported schema to IR")
    parser.add_argument("--schema-dir", default="schema/exported")
    parser.add_argument("--output", default="schema/ir/niri-ipc-ir.json")
    parser.add_argument("--upstream-pin", default="schema/upstream-pin.toml")
    args = parser.parse_args()

    schema_dir = Path(args.schema_dir)
    output = Path(args.output)
    pin_path = Path(args.upstream_pin)

    with open(pin_path, "rb") as f:
        pin = tomllib.load(f)

    upstream = pin["upstream"]

    schema_files = {
        "request": schema_dir / "request.schema.json",
        "reply": schema_dir / "reply.schema.json",
        "event": schema_dir / "event.schema.json",
        "action": schema_dir / "action.schema.json",
    }

    schemas = {}
    schema_hashes = {}
    all_defs = {}

    for key, path in schema_files.items():
        schema = load_schema(path)
        schemas[key] = schema
        schema_hashes[key] = hash_file(path)
        defs = schema.get("$defs", {})
        all_defs.update(defs)

    enums = build_enums(schemas, all_defs)
    structs = extract_structs(all_defs)

    ir = {
        "ir_version": "1",
        "upstream_crate": upstream["crate"],
        "upstream_version": upstream["version"],
        "upstream_features": upstream.get("features", []),
        "schema_hashes": schema_hashes,
        "types": enums + structs,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(ir, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote IR to {output}")


if __name__ == "__main__":
    main()
