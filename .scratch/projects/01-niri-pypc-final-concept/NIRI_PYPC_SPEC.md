# NIRI_PYPC_SPEC

Implementation specification for `niri-pypc`. This document translates the concept document into precise, implementable contracts: file-level module responsibilities, function signatures, data structures, state machines, and invariants. Every section is keyed to the concept section it implements.

---

## Table of Contents

1. [Notation and Conventions](#1-notation-and-conventions)
2. [Package Structure and Module Map](#2-package-structure-and-module-map)
3. [Schema Export Tool Specification](#3-schema-export-tool-specification)
4. [IR Normalization Tool Specification](#4-ir-normalization-tool-specification)
5. [Type Generator Tool Specification](#5-type-generator-tool-specification)
6. [Verification Tool Specification](#6-verification-tool-specification)
7. [Generated Type Module Specification](#7-generated-type-module-specification)
8. [Codec Module Specification](#8-codec-module-specification)
9. [Error Module Specification](#9-error-module-specification)
10. [Config Module Specification](#10-config-module-specification)
11. [Transport Module Specification](#11-transport-module-specification)
12. [Runtime Module Specification](#12-runtime-module-specification)
13. [API Module Specification](#13-api-module-specification)
14. [Public Package API Specification](#14-public-package-api-specification)
15. [Devenv Integration Specification](#15-devenv-integration-specification)
16. [Test Specification](#16-test-specification)

---

## 1. Notation and Conventions

**Implements concept:** Sections 3, 8

### Naming

- Package name: `niri-pypc`
- Import root: `niri_pypc`
- All Python identifiers follow PEP 8: `snake_case` for functions/variables/modules, `PascalCase` for classes.
- Generated Pydantic model names use `PascalCase` matching the Rust type name (e.g., `Output`, `Request`, `Action`).
- Generated field names use `snake_case` converted from Rust's `snake_case` (typically identity). Where the wire name differs from the Python name, `Field(alias="WireName")` is used.
- Reserved Python keywords in field names are suffixed with `_` (e.g., `type_` for `type`), with `alias="type"` preserving wire compatibility.

### Type Annotations

- All public functions and methods carry full type annotations.
- Use `T | None` union syntax (Python 3.10+), not `Optional[T]`.
- Use `list[T]`, `dict[K, V]` lowercase generics (Python 3.9+).
- Use `from __future__ import annotations` in all modules for forward reference support.

### Python Version

- Minimum: Python 3.13.
- May use 3.13 features: improved `asyncio.TaskGroup`, `type` statement, etc.

---

## 2. Package Structure and Module Map

**Implements concept:** Sections 9, 10, 11

```text
src/niri_pypc/
├─ __init__.py                  # Public re-exports (Section 14)
├─ _version.py                  # Package version constant
├─ errors.py                    # Error taxonomy (Section 9)
├─ config.py                    # Configuration and socket discovery (Section 10)
├─ types/
│  ├─ __init__.py               # Re-exports generated types + codec public API
│  ├─ codec.py                  # Externally-tagged enum encode/decode (Section 8)
│  ├─ helpers.py                # Shared type utilities
│  └─ generated/
│     ├─ __init__.py            # Re-exports all generated modules
│     ├─ _metadata.py           # Generation provenance
│     ├─ models.py              # Struct models (Output, Window, Workspace, etc.)
│     ├─ request.py             # Request enum + variants
│     ├─ reply.py               # Reply enum + variants
│     ├─ event.py               # Event enum + variants
│     └─ action.py              # Action enum + variants
├─ transport/
│  ├─ __init__.py
│  ├─ connection.py             # Raw Unix socket connection (Section 11)
│  └─ framing.py                # Newline-delimited frame read/write (Section 11)
├─ runtime/
│  ├─ __init__.py
│  └─ lifecycle.py              # Lifecycle state machine (Section 12)
└─ api/
   ├─ __init__.py
   ├─ client.py                 # NiriClient (Section 13)
   ├─ event_stream.py           # NiriEventStream (Section 13)
   └─ bundle.py                 # NiriConnectionBundle (Section 13)
```

### Dependency DAG (enforced, no cycles)

```
api.client      ──→ transport.connection, transport.framing, runtime.lifecycle, types, errors, config
api.event_stream ─→ transport.connection, transport.framing, runtime.lifecycle, types, errors, config
api.bundle      ──→ api.client, api.event_stream, errors, config
transport.*     ──→ runtime.lifecycle, errors
runtime.*       ──→ errors
types.*         ──→ (no internal deps outside types/)
errors          ──→ (no internal deps)
config          ──→ errors
```

---

## 3. Schema Export Tool Specification

**Implements concept:** Section 12

### Location

`tools/schema_exporter/`

### Purpose

Compile and run a Rust binary that uses `schemars::schema_for!()` to emit JSON Schema files for each top-level `niri-ipc` protocol type.

### Rust Crate Structure

```text
tools/schema_exporter/
├─ Cargo.toml
└─ src/
   └─ main.rs
```

### `Cargo.toml`

```toml
[package]
name = "niri-ipc-schema-exporter"
version = "0.1.0"
edition = "2021"

[dependencies]
niri-ipc = { version = "=25.11", features = ["json-schema"] }
schemars = "0.8"
serde_json = "1.0"
```

### `main.rs` Behavior

1. Accept an optional `--output-dir <path>` argument (default: `schema/exported/`).
2. Generate JSON Schema for each top-level type: `Request`, `Reply`, `Event`, `Action`.
3. Write each to `<output-dir>/<name>.schema.json` using `serde_json::to_string_pretty`.
4. Print each file path to stdout on success.
5. Exit 0 on success, non-zero on any error.

### Output Files

| File | Source Type |
|------|------------|
| `schema/exported/request.schema.json` | `niri_ipc::Request` |
| `schema/exported/reply.schema.json` | `niri_ipc::Reply` |
| `schema/exported/event.schema.json` | `niri_ipc::Event` |
| `schema/exported/action.schema.json` | `niri_ipc::Action` |

### Determinism

- `schemars` output for a fixed crate version is deterministic (same Rust compiler, same crate version → same JSON).
- The exporter must not inject timestamps, random values, or host-specific data.

---

## 4. IR Normalization Tool Specification

**Implements concept:** Section 13

### Location

`tools/normalize_ir.py`

### Purpose

Read exported JSON Schema files and produce a single normalized IR JSON file suitable for deterministic Python code generation.

### CLI Interface

```
python tools/normalize_ir.py \
  --schema-dir schema/exported/ \
  --output schema/ir/niri-ipc-ir.json \
  --upstream-pin schema/upstream-pin.toml
```

### Processing Steps

1. Read `upstream-pin.toml` to extract crate name, version, features.
2. Read each `*.schema.json` from `--schema-dir`.
3. Compute SHA-256 hash of each schema file (hex digest).
4. Resolve all `$ref` references within each schema.
5. Extract and classify type definitions:
   - **Enums**: types with `oneOf` or `anyOf` at the top level representing tagged unions.
   - **Structs**: types with `type: "object"` and `properties`.
   - **Newtypes**: single-field wrapper types.
6. For each enum, classify variants:
   - `unit`: variant is a plain string (no payload).
   - `newtype`: variant wraps a single inner type.
   - `struct`: variant carries named fields.
7. Normalize field types to a canonical set: `string`, `integer`, `float`, `boolean`, `array<T>`, `map<K,V>`, `option<T>`, `ref:TypeName`.
8. Sort all top-level types alphabetically by name.
9. Sort enum variants alphabetically by name.
10. Sort struct fields alphabetically by name.
11. Emit the IR JSON to `--output`.

### IR JSON Schema

```json
{
  "ir_version": "1",
  "upstream_crate": "niri-ipc",
  "upstream_version": "25.11",
  "upstream_features": ["json-schema"],
  "schema_hashes": {
    "request": "sha256:<hex>",
    "reply": "sha256:<hex>",
    "event": "sha256:<hex>",
    "action": "sha256:<hex>"
  },
  "types": [
    {
      "name": "Action",
      "kind": "enum",
      "tag_type": "external",
      "variants": [
        {
          "name": "CloseWindow",
          "kind": "unit"
        },
        {
          "name": "FocusColumnLeft",
          "kind": "unit"
        },
        {
          "name": "MoveWorkspaceToOutput",
          "kind": "newtype",
          "inner_type": "ref:OutputAction"
        },
        {
          "name": "Spawn",
          "kind": "struct",
          "fields": [
            { "name": "command", "type": "array<string>", "required": true }
          ]
        }
      ]
    },
    {
      "name": "Output",
      "kind": "struct",
      "fields": [
        { "name": "current_transform", "type": "ref:Transform", "required": true },
        { "name": "logical", "type": "option<ref:LogicalOutput>", "required": false },
        { "name": "name", "type": "string", "required": true },
        { "name": "physical", "type": "option<ref:PhysicalOutput>", "required": false }
      ]
    }
  ]
}
```

### Field Type Notation

| IR Type | Python Type | Pydantic |
|---------|-------------|----------|
| `string` | `str` | `str` |
| `integer` | `int` | `int` |
| `float` | `float` | `float` |
| `boolean` | `bool` | `bool` |
| `array<T>` | `list[T]` | `list[T]` |
| `map<K,V>` | `dict[K, V]` | `dict[K, V]` |
| `option<T>` | `T \| None` | `T \| None = None` |
| `ref:TypeName` | `TypeName` | `TypeName` (model reference) |

### Invariants

1. Same schema input → byte-for-byte identical IR output.
2. All sorting is lexicographic on the name key.
3. `ir_version` is bumped when the IR structure changes in a breaking way.
4. Schema hashes allow CI to detect upstream schema drift without re-running the Rust exporter.

---

## 5. Type Generator Tool Specification

**Implements concept:** Section 14

### Location

`tools/generate_types.py`

### Purpose

Read normalized IR and emit deterministic Pydantic v2 model code into `src/niri_pypc/types/generated/`.

### CLI Interface

```
python tools/generate_types.py \
  --ir schema/ir/niri-ipc-ir.json \
  --output-dir src/niri_pypc/types/generated/
```

### Output Files

| File | Contents |
|------|----------|
| `__init__.py` | Re-exports all public types from sub-modules |
| `_metadata.py` | Generation provenance constants |
| `models.py` | All struct-kind types as `BaseModel` subclasses |
| `request.py` | `Request` enum root model + per-variant models |
| `reply.py` | `Reply` enum root model + per-variant models |
| `event.py` | `Event` enum root model + per-variant models |
| `action.py` | `Action` enum root model + per-variant models |

### Generated File Header

Every generated file begins with:

```python
# AUTO-GENERATED by tools/generate_types.py — DO NOT EDIT
# upstream: niri-ipc 25.11
# ir_version: 1
# ir_hash: sha256:<hex>
```

### `_metadata.py`

```python
# AUTO-GENERATED by tools/generate_types.py — DO NOT EDIT

UPSTREAM_CRATE: str = "niri-ipc"
UPSTREAM_VERSION: str = "25.11"
GENERATOR_VERSION: str = "1"
IR_VERSION: str = "1"
IR_HASH: str = "sha256:<hex>"
SCHEMA_HASHES: dict[str, str] = {
    "request": "sha256:<hex>",
    "reply": "sha256:<hex>",
    "event": "sha256:<hex>",
    "action": "sha256:<hex>",
}
```

### Struct Model Generation Rules

For each IR type with `kind: "struct"`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Output(BaseModel):
    model_config = ConfigDict(populate_by_name=True, strict=False)

    name: str
    current_transform: Transform
    logical: LogicalOutput | None = None
    physical: PhysicalOutput | None = None
```

Rules:
1. Class name = IR `name` (PascalCase, already correct from Rust).
2. Fields sorted alphabetically to match IR ordering.
3. Required fields have no default. Optional fields default to `None`.
4. Fields whose wire name differs from the Python name use `Field(alias="wireName")`.
5. Reserved keywords get `_` suffix: `type_: str = Field(alias="type")`.
6. `model_config` with `populate_by_name=True` on every model to allow both alias and Python-name access.

### Enum Model Generation Rules

For each IR type with `kind: "enum"`, generate an externally-tagged union root model.

#### Unit Variant

```python
class VersionRequest(BaseModel):
    """Unit variant: serializes as the string "Version"."""
    pass
```

#### Newtype Variant

```python
class ActionRequest(BaseModel):
    """Newtype variant: wraps Action."""
    payload: Action
```

#### Struct Variant

```python
class SpawnAction(BaseModel):
    """Struct variant with inline fields."""
    command: list[str]
```

#### Root Enum Model

```python
from __future__ import annotations

import typing
from pydantic import BaseModel, model_validator, model_serializer


# Wire-name → variant class mapping
_REQUEST_VARIANTS: dict[str, type[BaseModel]] = {
    "Version": VersionRequest,
    "Action": ActionRequest,
    "EventStream": EventStreamRequest,
    # ...
}

# Variant class → wire-name mapping (for serialization)
_REQUEST_VARIANT_NAMES: dict[type[BaseModel], str] = {
    v: k for k, v in _REQUEST_VARIANTS.items()
}


class Request(BaseModel):
    """
    Externally-tagged enum. Wire format: {"VariantName": payload} or "VariantName".
    """
    variant: typing.Annotated[
        VersionRequest | ActionRequest | EventStreamRequest,  # | ...
        # Union of all known variant types
    ]

    @model_validator(mode="before")
    @classmethod
    def _decode_external_tag(cls, data: typing.Any) -> dict[str, typing.Any]:
        from niri_pypc.types.codec import decode_externally_tagged
        return {"variant": decode_externally_tagged(data, _REQUEST_VARIANTS)}

    @model_serializer
    def _encode_external_tag(self) -> dict[str, typing.Any] | str:
        from niri_pypc.types.codec import encode_externally_tagged
        return encode_externally_tagged(self.variant, _REQUEST_VARIANT_NAMES)
```

#### Unknown Sentinel (inbound enums only: Reply, Event)

```python
class UnknownEvent(BaseModel):
    """Sentinel for unrecognized event variants. Carries raw payload for diagnostics."""
    variant_name: str
    raw_payload: typing.Any
```

For inbound enums (`Reply`, `Event`), the `_decode_external_tag` validator includes a fallback:

```python
@model_validator(mode="before")
@classmethod
def _decode_external_tag(cls, data: typing.Any) -> dict[str, typing.Any]:
    from niri_pypc.types.codec import decode_externally_tagged
    return {"variant": decode_externally_tagged(
        data,
        _EVENT_VARIANTS,
        unknown_sentinel=UnknownEvent,
    )}
```

### Name Normalization

| Rust Name | Python Name | Rule |
|-----------|-------------|------|
| `FocusColumnLeft` | `FocusColumnLeftAction` | Variant class: append parent enum name |
| `Output` | `Output` | Struct: identity |
| `type` | `type_` | Reserved keyword: append `_` |
| `id` | `id` | Not reserved in Python |

Variant class names are `{VariantName}{EnumName}` to avoid collisions (e.g., `VersionRequest`, `VersionReply`). The root enum model is just `Request`, `Reply`, `Event`, `Action`.

---

## 6. Verification Tool Specification

**Implements concept:** Section 14 (invariant 1), Section 26 (CI gate 4)

### Location

`tools/verify_generated.py`

### Purpose

Verify that committed generated code matches what the generator would produce from current IR.

### CLI Interface

```
python tools/verify_generated.py \
  --ir schema/ir/niri-ipc-ir.json \
  --generated-dir src/niri_pypc/types/generated/
```

### Behavior

1. Generate types to a temporary directory using the same logic as `generate_types.py`.
2. Diff every file in the temp directory against `--generated-dir`.
3. If any file differs or is missing, print the diff and exit with code 1.
4. If all files match, print "Generated code is up to date." and exit 0.

---

## 7. Generated Type Module Specification

**Implements concept:** Sections 13, 15

This section specifies the runtime behavior of the generated Pydantic models.

### Struct Models

All struct models inherit from `BaseModel` with:

```python
model_config = ConfigDict(
    populate_by_name=True,
    strict=False,
)
```

- `populate_by_name=True`: allows constructing with Python field names even when aliases are defined.
- `strict=False`: allows coercion (e.g., string `"123"` → int `123`) matching serde's flexible deserialization.

### Enum Root Models

Enum root models (`Request`, `Reply`, `Event`, `Action`) wrap a single `variant` field containing the decoded variant model instance.

**Decode (inbound):**
1. Input is raw parsed JSON (dict or string).
2. `model_validator(mode="before")` intercepts, calls `codec.decode_externally_tagged()`.
3. Returns `{"variant": <variant_model_instance>}`.

**Encode (outbound):**
1. `model_serializer` calls `codec.encode_externally_tagged()`.
2. Returns the externally-tagged dict (e.g., `{"Action": {...}}`) or string (e.g., `"Version"`).

### Type Dispatch Tables

Each enum module exports two dicts:

```python
_VARIANTS: dict[str, type[BaseModel]] = { ... }       # wire-name → model class
_VARIANT_NAMES: dict[type[BaseModel], str] = { ... }   # model class → wire-name
```

These are used by `codec.py` and are the single source of truth for variant resolution.

---

## 8. Codec Module Specification

**Implements concept:** Section 16

### Location

`src/niri_pypc/types/codec.py`

### Purpose

Hand-written encode/decode primitives for externally-tagged enums and Reply Ok/Err unwrapping.

### Functions

#### `decode_externally_tagged`

```python
def decode_externally_tagged(
    data: Any,
    variants: dict[str, type[BaseModel]],
    *,
    unknown_sentinel: type[BaseModel] | None = None,
) -> BaseModel:
    """
    Decode an externally-tagged serde enum value.

    Args:
        data: Raw JSON-parsed value. Either:
              - A dict with exactly one key (the variant name) and the payload as value.
              - A string (unit variant name).
        variants: Wire-name → variant model class mapping.
        unknown_sentinel: If provided and the variant name is not in `variants`,
                          construct this model with variant_name and raw_payload.
                          If None, raise DecodeError for unknown variants.

    Returns:
        An instance of the matched variant model.

    Raises:
        DecodeError: If data shape is invalid or variant is unknown (without sentinel).
    """
```

**Logic:**
1. If `data` is a `str`: look up in `variants`. If found, construct with no args (unit variant). If not found, use sentinel or raise.
2. If `data` is a `dict` with exactly one key: extract `(variant_name, payload)`. Look up `variant_name` in `variants`. If found, construct: `VariantClass.model_validate(payload)` for struct variants, `VariantClass(payload=payload)` for newtype variants. If not found, use sentinel or raise.
3. Otherwise: raise `DecodeError` with details about the unexpected shape.

#### `encode_externally_tagged`

```python
def encode_externally_tagged(
    variant: BaseModel,
    variant_names: dict[type[BaseModel], str],
) -> dict[str, Any] | str:
    """
    Encode a variant model instance into externally-tagged wire format.

    Args:
        variant: The variant model instance.
        variant_names: Model class → wire-name mapping.

    Returns:
        For unit variants: the wire name as a string.
        For newtype/struct variants: {"WireName": payload_dict}.

    Raises:
        EncodeError (subclass of NiriError): If variant type is not in mapping.
    """
```

**Logic:**
1. Look up `type(variant)` in `variant_names` to get the wire name.
2. If variant has no fields (unit): return wire name as string.
3. If variant has a single `payload` field (newtype): return `{wire_name: variant.payload.model_dump(by_alias=True)}` if payload is a model, else `{wire_name: variant.payload}`.
4. If variant has multiple fields (struct): return `{wire_name: variant.model_dump(by_alias=True)}`.

#### `unwrap_reply`

```python
def unwrap_reply(data: dict[str, Any]) -> Any:
    """
    Unwrap a niri Reply envelope.

    Niri responses are {"Ok": <payload>} or {"Err": "<message>"}.

    Args:
        data: Raw parsed JSON response dict.

    Returns:
        The Ok payload value.

    Raises:
        RemoteError: If the response is an Err.
        DecodeError: If the response shape is neither Ok nor Err.
    """
```

---

## 9. Error Module Specification

**Implements concept:** Section 24

### Location

`src/niri_pypc/errors.py`

### Class Hierarchy

```python
class NiriError(Exception):
    """Base exception for all niri-pypc errors."""

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        socket_path: str | None = None,
        retryable: bool = False,
    ) -> None: ...


class TransportError(NiriError):
    """Socket or framing I/O failure."""


class NiriTimeoutError(NiriError, TimeoutError):
    """Connect, request, or event read timeout.

    Inherits from both NiriError and builtins.TimeoutError so callers
    can catch either."""


class DecodeError(NiriError):
    """Validation or shape failure during decode.

    Attributes:
        raw_payload: Bounded excerpt of the raw data that failed decoding.
    """

    def __init__(
        self,
        message: str,
        *,
        raw_payload: str | None = None,
        **kwargs: Any,
    ) -> None: ...


class ProtocolError(NiriError):
    """Wire-level contract violation (e.g., unexpected frame structure)."""


class RemoteError(NiriError):
    """Error response from the compositor ("Err" reply).

    Attributes:
        remote_message: The error string returned by niri.
    """

    def __init__(
        self,
        message: str,
        *,
        remote_message: str,
        **kwargs: Any,
    ) -> None: ...


class LifecycleError(NiriError):
    """Invalid state transition or usage (e.g., request on closed client).

    Attributes:
        state: The lifecycle state when the error occurred.
    """

    def __init__(
        self,
        message: str,
        *,
        state: str | None = None,
        **kwargs: Any,
    ) -> None: ...


class ConfigError(NiriError):
    """Invalid or unresolved configuration."""


class InternalError(NiriError):
    """Impossible internal state — indicates a bug in niri-pypc."""
```

### Design Rules

1. All errors carry an `operation` field (e.g., `"connect"`, `"request"`, `"read_event"`).
2. `socket_path` is populated whenever a socket is involved.
3. `retryable` is a hint — `True` for transient I/O failures, `False` for protocol/decode/lifecycle errors.
4. Wrapped causes use `raise XError(...) from original_exception`.
5. `raw_payload` in `DecodeError` is truncated to 1024 characters max.

---

## 10. Config Module Specification

**Implements concept:** Section 17

### Location

`src/niri_pypc/config.py`

### `NiriConfig` Model

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NiriConfig:
    """Configuration for niri-pypc connections."""

    socket_path: Path | None = None
    connect_timeout: float = 5.0
    request_timeout: float = 10.0
    event_read_timeout: float | None = None
    max_frame_size: int = 4 * 1024 * 1024  # 4 MiB
    event_queue_capacity: int = 256
    strict_version_check: bool = True
    backpressure_mode: BackpressureMode = BackpressureMode.DROP_OLDEST

    def resolve_socket_path(self) -> Path:
        """Resolve the socket path using the precedence chain.

        1. self.socket_path if set.
        2. NIRI_SOCKET environment variable.
        3. Raise ConfigError.

        Returns:
            Resolved Path to the Unix socket.

        Raises:
            ConfigError: If no socket path can be resolved.
        """
        if self.socket_path is not None:
            return self.socket_path
        env = os.environ.get("NIRI_SOCKET")
        if env:
            return Path(env)
        raise ConfigError(
            "No socket path: set socket_path or NIRI_SOCKET environment variable",
            operation="resolve_socket_path",
        )
```

### `BackpressureMode` Enum

```python
import enum


class BackpressureMode(enum.Enum):
    DROP_OLDEST = "drop_oldest"
    FAIL_FAST = "fail_fast"
```

---

## 11. Transport Module Specification

**Implements concept:** Section 18

### `transport/connection.py`

Manages raw asyncio Unix socket connections.

```python
from __future__ import annotations

import asyncio
from pathlib import Path


class UnixConnection:
    """Raw Unix socket connection wrapper.

    Manages a single asyncio StreamReader/StreamWriter pair.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        socket_path: Path,
    ) -> None: ...

    @classmethod
    async def connect(
        cls,
        socket_path: Path,
        *,
        timeout: float = 5.0,
    ) -> UnixConnection:
        """Open a Unix domain socket connection.

        Raises:
            TransportError: If the socket cannot be reached.
            NiriTimeoutError: If connection exceeds timeout.
        """

    async def write_frame(self, data: bytes) -> None:
        """Write a newline-terminated frame.

        Raises:
            TransportError: On write failure.
        """

    async def read_frame(
        self,
        *,
        max_size: int = 4 * 1024 * 1024,
        timeout: float | None = None,
    ) -> bytes:
        """Read a newline-terminated frame.

        Args:
            max_size: Maximum frame size in bytes. Frames exceeding this raise ProtocolError.
            timeout: Read timeout in seconds. None = no timeout.

        Returns:
            Raw frame bytes (without trailing newline).

        Raises:
            TransportError: On read failure or unexpected EOF.
            NiriTimeoutError: On timeout.
            ProtocolError: If frame exceeds max_size.
        """

    async def close(self) -> None:
        """Close the connection. Idempotent."""

    @property
    def is_closed(self) -> bool: ...
```

### `transport/framing.py`

JSON frame encoding/decoding.

```python
from __future__ import annotations

import json
from typing import Any


def encode_frame(data: Any) -> bytes:
    """Serialize data to a newline-terminated JSON frame.

    Args:
        data: JSON-serializable value.

    Returns:
        UTF-8 encoded JSON bytes with trailing newline.
    """
    return json.dumps(data, separators=(",", ":")).encode("utf-8") + b"\n"


def decode_frame(raw: bytes) -> Any:
    """Deserialize a raw frame into a Python object.

    Args:
        raw: Raw frame bytes (newline already stripped).

    Returns:
        Parsed JSON value.

    Raises:
        DecodeError: If JSON parsing fails.
    """
```

---

## 12. Runtime Module Specification

**Implements concept:** Sections 18, 19

### `runtime/lifecycle.py`

State machine for connection lifecycle.

```python
from __future__ import annotations

import enum
import asyncio


class LifecycleState(enum.Enum):
    INIT = "init"
    CONNECTING = "connecting"
    READY = "ready"
    CLOSING = "closing"
    CLOSED = "closed"


class LifecycleManager:
    """Manages lifecycle state transitions and enforces invariants.

    Thread-safe: uses asyncio.Lock for state transitions.
    """

    def __init__(self) -> None:
        self._state: LifecycleState = LifecycleState.INIT
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def state(self) -> LifecycleState: ...

    async def transition_to(self, target: LifecycleState) -> None:
        """Transition to a new state.

        Valid transitions:
            INIT → CONNECTING
            CONNECTING → READY
            CONNECTING → CLOSED (connect failure)
            READY → CLOSING
            CLOSING → CLOSED
            any → CLOSED (via close())

        Raises:
            LifecycleError: On invalid transition.
        """

    def require_state(self, *allowed: LifecycleState) -> None:
        """Assert current state is one of the allowed states.

        Raises:
            LifecycleError: If current state is not in allowed set.
        """

    @property
    def is_usable(self) -> bool:
        """True if state is READY."""
        return self._state == LifecycleState.READY

    @property
    def is_terminal(self) -> bool:
        """True if state is CLOSED."""
        return self._state == LifecycleState.CLOSED
```

### State Transition Diagram

```
INIT ──→ CONNECTING ──→ READY ──→ CLOSING ──→ CLOSED
              │                                  ↑
              └──────────────────────────────────┘
                       (connect failure)
```

Any state can transition to `CLOSED` via explicit `close()`.

---

## 13. API Module Specification

**Implements concept:** Sections 18, 19, 20, 22, 23

### `api/client.py` — `NiriClient`

```python
from __future__ import annotations

from typing import Any
from pydantic import BaseModel

from niri_pypc.config import NiriConfig


class NiriClient:
    """Command client for niri IPC.

    Uses one-connection-per-request model: each request() call opens a new
    Unix socket connection, sends the request, reads the response, and closes.

    Usage:
        async with NiriClient.connect(config) as client:
            version = await client.request(VersionRequest())
    """

    def __init__(self, config: NiriConfig) -> None: ...

    @classmethod
    async def connect(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriClient:
        """Create a client. Validates config but does not open a socket yet.

        Returns an async context manager.
        """

    async def request(self, req: BaseModel, *, timeout: float | None = None) -> Any:
        """Send a request and return the decoded response payload.

        Flow:
        1. Resolve socket path from config.
        2. Open a new UnixConnection.
        3. Encode request via model's serializer → JSON frame.
        4. Write frame to socket.
        5. Read response frame.
        6. Unwrap Reply Ok/Err via codec.unwrap_reply().
        7. Close connection.
        8. Return decoded payload.

        Args:
            req: A request variant model instance (e.g., VersionRequest()).
            timeout: Override request timeout. If None, use config.request_timeout.

        Returns:
            The decoded Ok payload from the compositor's response.

        Raises:
            TransportError: Socket I/O failure.
            NiriTimeoutError: Request exceeded timeout.
            DecodeError: Response could not be decoded.
            RemoteError: Compositor returned an Err response.
            LifecycleError: Client has been closed.
        """

    async def close(self) -> None:
        """Close the client. Idempotent.

        After close(), all subsequent request() calls raise LifecycleError.
        """

    async def __aenter__(self) -> NiriClient: ...
    async def __aexit__(self, *exc: Any) -> None: ...
```

### `api/event_stream.py` — `NiriEventStream`

```python
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from pydantic import BaseModel

from niri_pypc.config import NiriConfig


class NiriEventStream:
    """Event stream client for niri IPC.

    Opens a single persistent connection, sends an EventStream request,
    and yields decoded events.

    Usage:
        async with NiriEventStream.connect(config) as stream:
            async for event in stream:
                handle(event)
    """

    def __init__(self, config: NiriConfig) -> None: ...

    @classmethod
    async def connect(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriEventStream:
        """Connect to the niri event socket.

        Flow:
        1. Resolve socket path.
        2. Open UnixConnection.
        3. Send EventStream request frame.
        4. Transition to READY.
        5. Start background reader task that decodes events into the queue.
        """

    async def next(self, *, timeout: float | None = None) -> BaseModel:
        """Read the next event from the stream.

        Args:
            timeout: Seconds to wait. None uses config.event_read_timeout.

        Returns:
            A decoded event variant model instance.

        Raises:
            NiriTimeoutError: If timeout expires with no event.
            TransportError: If the connection has been lost.
            LifecycleError: If the stream has been closed.
        """

    def __aiter__(self) -> AsyncIterator[BaseModel]: ...

    async def __anext__(self) -> BaseModel:
        """Yield next event. Raises StopAsyncIteration on stream close."""

    async def close(self) -> None:
        """Close the event stream. Idempotent.

        1. Transition lifecycle to CLOSING.
        2. Cancel background reader task.
        3. Close UnixConnection.
        4. Drain remaining queued events.
        5. Transition to CLOSED.
        """

    async def __aenter__(self) -> NiriEventStream: ...
    async def __aexit__(self, *exc: Any) -> None: ...
```

#### Background Reader Task

The event stream runs a background `asyncio.Task` that:
1. Reads frames from the connection in a loop.
2. Decodes each frame as an `Event` via the generated model.
3. Puts decoded events into an `asyncio.Queue` bounded by `config.event_queue_capacity`.
4. On queue full:
   - `DROP_OLDEST` mode: pop the oldest event, log a warning, push the new one.
   - `FAIL_FAST` mode: close the stream with a backpressure error.
5. On connection error or EOF: close the stream and push a sentinel/exception.
6. On cancellation: exit cleanly.

### `api/bundle.py` — `NiriConnectionBundle`

```python
from __future__ import annotations

from typing import Any

from niri_pypc.config import NiriConfig
from niri_pypc.api.client import NiriClient
from niri_pypc.api.event_stream import NiriEventStream


class NiriConnectionBundle:
    """Convenience wrapper holding both a command client and event stream.

    Lifetime semantics:
    - Closing the bundle closes both members.
    - Members have independent error isolation: one failing does not
      force-close the other.
    - Access members via .client and .events properties.
    """

    def __init__(self, client: NiriClient, events: NiriEventStream) -> None: ...

    @classmethod
    async def open(
        cls,
        config: NiriConfig | None = None,
    ) -> NiriConnectionBundle:
        """Open both command and event connections.

        If event stream connection fails after client succeeds,
        the client is closed before raising.
        """

    @property
    def client(self) -> NiriClient: ...

    @property
    def events(self) -> NiriEventStream: ...

    async def close(self) -> None:
        """Close both connections. Idempotent.

        Closes both members, suppressing secondary close errors.
        """

    async def __aenter__(self) -> NiriConnectionBundle: ...
    async def __aexit__(self, *exc: Any) -> None: ...
```

---

## 14. Public Package API Specification

**Implements concept:** Section 23

### `src/niri_pypc/__init__.py`

The top-level `__init__.py` re-exports the public API surface:

```python
"""niri-pypc: Python protocol client for the niri Wayland compositor."""

from niri_pypc._version import __version__
from niri_pypc.config import NiriConfig, BackpressureMode
from niri_pypc.errors import (
    NiriError,
    TransportError,
    NiriTimeoutError,
    DecodeError,
    ProtocolError,
    RemoteError,
    LifecycleError,
    ConfigError,
    InternalError,
)
from niri_pypc.api.client import NiriClient
from niri_pypc.api.event_stream import NiriEventStream
from niri_pypc.api.bundle import NiriConnectionBundle

# Generated types are accessed via niri_pypc.types
# e.g., from niri_pypc.types import Request, Event, Action
```

### `src/niri_pypc/types/__init__.py`

Re-exports from generated modules:

```python
"""Protocol types for niri IPC."""

from niri_pypc.types.generated import *  # noqa: F401,F403
from niri_pypc.types.codec import (
    decode_externally_tagged,
    encode_externally_tagged,
    unwrap_reply,
)
```

### Import Conventions for Users

```python
# Client usage
from niri_pypc import NiriClient, NiriConfig
from niri_pypc.types import Request, VersionRequest, Event

# Error handling
from niri_pypc import NiriError, RemoteError, NiriTimeoutError

# Advanced: codec access
from niri_pypc.types.codec import decode_externally_tagged
```

---

## 15. Devenv Integration Specification

**Implements concept:** Section 12 (devenv), Section 29 (Phase A)

### `devenv.nix` Additions

```nix
{
  packages = [
    pkgs.git
    pkgs.uv
  ];

  languages = {
    python = {
      enable = true;
      version = "3.13";
      venv.enable = true;
      uv.enable = true;
    };
    rust = {
      enable = true;
      channel = "stable";
    };
  };

  scripts = {
    export-schema.exec = ''
      cd tools/schema_exporter && cargo run --release -- --output-dir ../../schema/exported/
    '';
    normalize-ir.exec = ''
      python tools/normalize_ir.py \
        --schema-dir schema/exported/ \
        --output schema/ir/niri-ipc-ir.json \
        --upstream-pin schema/upstream-pin.toml
    '';
    generate-types.exec = ''
      python tools/generate_types.py \
        --ir schema/ir/niri-ipc-ir.json \
        --output-dir src/niri_pypc/types/generated/
    '';
    verify-generated.exec = ''
      python tools/verify_generated.py \
        --ir schema/ir/niri-ipc-ir.json \
        --generated-dir src/niri_pypc/types/generated/
    '';
    regen-all.exec = ''
      export-schema && normalize-ir && generate-types
    '';
  };
}
```

### Workflow Commands

| Command | Purpose |
|---------|---------|
| `devenv shell -- export-schema` | Run Rust exporter, write JSON Schemas |
| `devenv shell -- normalize-ir` | Normalize schemas into IR |
| `devenv shell -- generate-types` | Generate Pydantic models from IR |
| `devenv shell -- verify-generated` | Verify committed generated code is up to date |
| `devenv shell -- regen-all` | Full pipeline: export → normalize → generate |

---

## 16. Test Specification

**Implements concept:** Section 25

### Test Directory Structure

```text
tests/
├─ conftest.py                  # Shared fixtures
├─ types/
│  ├─ conftest.py
│  ├─ test_roundtrip.py         # Encode → decode → encode for all types
│  ├─ test_golden.py            # Golden fixture assertions
│  ├─ test_unknown_variants.py  # Unknown sentinel behavior
│  ├─ test_edge_cases.py        # Null/missing/empty/reserved-word fields
│  └─ test_metadata.py          # _metadata.py provenance checks
├─ transport/
│  ├─ conftest.py
│  ├─ test_framing.py           # Frame encode/decode, oversize, partial
│  └─ test_connection.py        # Connect/close, timeout, EOF handling
├─ api/
│  ├─ conftest.py
│  ├─ test_client.py            # Request/response via mock socket
│  ├─ test_event_stream.py      # Event streaming, backpressure, close
│  └─ test_bundle.py            # Bundle open/close, member independence
├─ integration/
│  ├─ conftest.py               # Mock niri socket server fixture
│  ├─ test_command_flow.py      # Full command request/response cycle
│  ├─ test_event_flow.py        # Full event subscription cycle
│  └─ test_independence.py      # Command/event socket independence
├─ live/
│  ├─ conftest.py               # Skip if NIRI_SOCKET not set
│  └─ test_live.py              # Version query against real niri
└─ fixtures/
   ├─ golden/                   # Golden JSON fixtures per type
   └─ schemas/                  # Test schema fragments
```

### Key Test Fixtures

#### Mock Niri Socket Server

```python
# tests/integration/conftest.py

import asyncio
import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
async def mock_niri_server():
    """Async fixture providing a mock niri Unix socket server.

    Yields (socket_path, server_control) where server_control allows
    setting up canned responses and inspecting received requests.
    """
    ...
```

The mock server:
1. Listens on a temporary Unix socket.
2. For each connection, reads one frame (request).
3. If the request is `"EventStream"` or `{"EventStream": ...}`, enters streaming mode and sends configured events.
4. Otherwise, sends a configured response and closes.
5. Records all received requests for assertions.

#### Live Test Skip

```python
# tests/live/conftest.py

import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("NIRI_SOCKET"),
    reason="NIRI_SOCKET not set — skipping live tests",
)
```

### Test Categories and Examples

#### `test_roundtrip.py`

```python
async def test_request_version_roundtrip():
    """Version request encodes to "Version" and decodes back."""
    req = VersionRequest()
    encoded = Request(variant=req).model_dump(mode="json")
    assert encoded == "Version"
    decoded = Request.model_validate("Version")
    assert isinstance(decoded.variant, VersionRequest)
```

#### `test_unknown_variants.py`

```python
async def test_unknown_event_produces_sentinel():
    """An unrecognized event variant produces UnknownEvent sentinel."""
    raw = {"NewFutureEvent": {"some": "data"}}
    event = Event.model_validate(raw)
    assert isinstance(event.variant, UnknownEvent)
    assert event.variant.variant_name == "NewFutureEvent"
    assert event.variant.raw_payload == {"some": "data"}
```

#### `test_framing.py`

```python
async def test_oversize_frame_rejected():
    """Frames exceeding max_size raise ProtocolError."""
    conn = ...  # mock connection
    # Send a frame larger than max_size
    with pytest.raises(ProtocolError):
        await conn.read_frame(max_size=100)
```

#### `test_client.py`

```python
async def test_request_returns_decoded_reply(mock_niri_server):
    """Client.request() returns the decoded Ok payload."""
    socket_path, server = mock_niri_server
    server.set_response({"Ok": "0.1.0"})

    config = NiriConfig(socket_path=socket_path)
    async with NiriClient.connect(config) as client:
        result = await client.request(VersionRequest())
    assert result == "0.1.0"
```

#### `test_event_stream.py`

```python
async def test_event_stream_yields_events(mock_niri_server):
    """EventStream yields decoded events in order."""
    socket_path, server = mock_niri_server
    server.set_events([
        {"WorkspaceActivated": {"id": 1, "focused": True}},
        {"WorkspaceActivated": {"id": 2, "focused": False}},
    ])

    config = NiriConfig(socket_path=socket_path)
    async with NiriEventStream.connect(config) as stream:
        e1 = await stream.next(timeout=1.0)
        e2 = await stream.next(timeout=1.0)
    # Assert event types and field values
```

#### `test_bundle.py`

```python
async def test_bundle_member_independence(mock_niri_server):
    """Event stream error does not close command client."""
    socket_path, server = mock_niri_server
    server.set_response({"Ok": "0.1.0"})
    server.set_events([])  # EOF immediately

    config = NiriConfig(socket_path=socket_path)
    async with NiriConnectionBundle.open(config) as bundle:
        # Event stream should hit EOF
        # But client should still work
        result = await bundle.client.request(VersionRequest())
        assert result == "0.1.0"
```

---

*End of specification.*
