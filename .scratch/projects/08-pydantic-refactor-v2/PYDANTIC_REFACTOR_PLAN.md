Below is the implementation plan I would hand to the agent. It assumes we are doing a full cutover to the new architecture with no compatibility layer and no transitional API shims. It is grounded in the current repo and the demo failures already identified in the error report. 

## Refactor goal

Refactor `niri-pypc` so that:

* protocol truth is represented explicitly in generated models,
* externally tagged enums are real `RootModel`s,
* variant kind is preserved as metadata, never inferred from field shape,
* transport edges use Pydantic JSON APIs directly,
* event stream bootstrap is explicit and validated,
* tests and fixtures enforce the real protocol rather than the current accidental behavior.

## Non-goals

Do **not**:

* preserve `.variant` wrapper APIs,
* preserve old test expectations,
* add compatibility shims,
* patch generated files by hand as a long-term solution.

This should be one cohesive refactor.

---

# Phase 0 — Working rules before touching code

## 0.1 Create a short-lived refactor branch

Create a dedicated refactor branch and keep the work atomic.

## 0.2 Do not edit generated files manually except for inspection

Only change:

* `tools/generate_types.py`
* handwritten runtime modules
* tests
* demo
* harness/docs

Then regenerate.

## 0.3 Take one baseline snapshot

Run these once and save the output in a scratch note:

```bash
pytest -q
python tools/verify_generated.py
rg -n '\.variant|variant=' src tests demo
```

That grep list is your kill list. Every remaining `.variant` access should be intentional and temporary until the cutover is complete.

---

# Phase 1 — Introduce the new protocol base layer

## Files to add

* `src/niri_pypc/types/base.py`

## Files to update

* `src/niri_pypc/types/__init__.py`

## Goal

Create one small handwritten runtime foundation that all generated protocol types inherit from.

## 1.1 Add `types/base.py`

Use this as the starting shape:

```python
from __future__ import annotations

from functools import lru_cache
from typing import Any, ClassVar, Generic, Literal, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict, RootModel, model_serializer, model_validator

VariantKind: TypeAlias = Literal["unit", "newtype", "struct"]


class ProtocolModel(BaseModel):
    """Base for all generated protocol models."""

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
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


class ExternallyTaggedEnum(RootModel[RootT], Generic[RootT]):
    """Generic RootModel for externally-tagged enums."""

    __niri_variants__: ClassVar[tuple[type[ProtocolVariant], ...]]
    __niri_unknown_variant_model__: ClassVar[type[ProtocolModel] | None] = None

    @model_validator(mode="before")
    @classmethod
    def _decode_root(cls, data: Any) -> Any:
        from niri_pypc.types.codec import decode_externally_tagged

        if isinstance(data, cls):
            return data

        if isinstance(data, ProtocolModel):
            return {"root": data}

        decoded = decode_externally_tagged(
            data,
            cls._variant_map(),
            unknown_variant_model=cls.__niri_unknown_variant_model__,
        )
        return {"root": decoded}

    @model_serializer(mode="plain")
    def _encode_root(self) -> Any:
        from niri_pypc.types.codec import encode_externally_tagged

        return encode_externally_tagged(self.root)

    @classmethod
    @lru_cache(maxsize=None)
    def _variant_map(cls) -> dict[str, type[ProtocolVariant]]:
        return {
            variant.__niri_wire_name__: variant
            for variant in cls.__niri_variants__
        }
```

## 1.2 Update `types/__init__.py`

Export the new base types:

```python
from niri_pypc.types.base import (
    ExternallyTaggedEnum,
    ProtocolModel,
    ProtocolVariant,
    UnknownEvent,
)
from niri_pypc.types.codec import decode_externally_tagged, encode_externally_tagged
from niri_pypc.types.generated import *  # noqa: F401,F403
```

## 1.3 Add first unit tests now

Create a new test file:

* `tests/types/test_base_runtime.py`

Test only handwritten base behavior with tiny fake models, not generated types yet.

Example:

```python
from niri_pypc.types.base import ExternallyTaggedEnum, ProtocolVariant

class Ping(ProtocolVariant):
    __niri_wire_name__ = "Ping"
    __niri_variant_kind__ = "unit"

class Echo(ProtocolVariant):
    __niri_wire_name__ = "Echo"
    __niri_variant_kind__ = "newtype"

    payload: str

PingOrEcho = Ping | Echo

class Sample(ExternallyTaggedEnum[PingOrEcho]):
    __niri_variants__ = (Ping, Echo)

def test_root_model_round_trip_unit():
    value = Sample(root=Ping())
    assert value.model_dump(mode="json") == "Ping"

def test_root_model_round_trip_newtype():
    value = Sample(root=Echo(payload="hi"))
    assert value.model_dump(mode="json") == {"Echo": "hi"}
```

### Acceptance criteria

* Base layer exists and is clean.
* No generated code depends on it yet.
* Tests for base behavior pass.

---

# Phase 2 — Rewrite the codec to be metadata-driven

## File to rewrite

* `src/niri_pypc/types/codec.py`

## Goal

Delete all field-shape heuristics. The codec must use explicit metadata only.

## 2.1 Replace the entire module

Start from this shape:

```python
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
```

## 2.2 Delete `unwrap_reply()` from `codec.py`

That logic belongs on `Reply`, not in a loose helper.

## 2.3 Add codec contract tests

Create:

* `tests/types/test_codec_contract.py`

Required cases:

```python
def test_unit_variant_encodes_to_string(): ...
def test_newtype_variant_encodes_to_tagged_scalar(): ...
def test_zero_field_struct_encodes_to_tagged_empty_object(): ...
def test_struct_variant_rejects_string_form(): ...
def test_unit_variant_rejects_object_form(): ...
def test_unknown_event_returns_unknown_sentinel(): ...
```

### Acceptance criteria

* The codec has zero `model_fields` heuristics.
* Zero-field structs are encoded as `{wire_name: {}}`.
* No reply-unwrapping helper remains in `codec.py`.

---

# Phase 3 — Rewrite the generator

## File to rewrite

* `tools/generate_types.py`

## Goal

Regenerate every protocol type from the new architecture, not by layering hacks onto the current generator.

## 3.1 Add new codegen strategies

The generator should now support three distinct outputs:

1. ordinary structs -> `ProtocolModel`
2. mixed externally tagged enums -> `ProtocolVariant` subclasses + `ExternallyTaggedEnum`
3. all-unit enums -> `StrEnum`

## 3.2 Add new helper functions

Add helpers like:

```python
def is_all_unit_enum(ir_type: dict) -> bool:
    return ir_type["kind"] == "enum" and all(v["kind"] == "unit" for v in ir_type["variants"])


def safe_enum_member_name(name: str) -> str:
    candidate = name.upper().replace("-", "_")
    if candidate[0].isdigit():
        candidate = f"VALUE_{candidate}"
    if candidate in RESERVED_WORDS:
        candidate = f"{candidate}_"
    return candidate
```

## 3.3 Replace `gen_struct_code()`

Use `ProtocolModel`, not raw `BaseModel`:

```python
def gen_struct_code(ir_type: dict) -> str:
    lines = [f"class {ir_type['name']}(ProtocolModel):"]
    fields = ir_type.get("fields", [])
    if not fields:
        lines.append("    pass")
        return "\n".join(lines)

    for f in fields:
        py_type = ir_type_to_python(f["type"])
        field_name = safe_field_name(f["name"])
        if f["required"]:
            lines.append(f"    {field_name}: {py_type}")
        else:
            lines.append(f"    {field_name}: {py_type} = None")
    return "\n".join(lines)
```

## 3.4 Replace `gen_variant_code()`

It must preserve IR kind explicitly:

```python
def gen_variant_code(variant: dict, enum_name: str) -> str:
    cls_name = variant_class_name(variant["name"], enum_name)
    kind = variant["kind"]
    lines = [
        f"class {cls_name}(ProtocolVariant):",
        f'    __niri_wire_name__ = "{variant["name"]}"',
        f'    __niri_variant_kind__ = "{kind}"',
    ]

    if kind == "unit":
        lines.append("    pass")
    elif kind == "newtype":
        py_type = ir_type_to_python(variant.get("inner_type", "string"))
        lines.append(f"    payload: {py_type}")
    elif kind == "struct":
        fields = variant.get("fields", [])
        if not fields:
            lines.append("    pass")
        else:
            for f in fields:
                py_type = ir_type_to_python(f["type"])
                field_name = safe_field_name(f["name"])
                if f["required"]:
                    lines.append(f"    {field_name}: {py_type}")
                else:
                    lines.append(f"    {field_name}: {py_type} = None")
    else:
        raise ValueError(f"Unsupported variant kind: {kind}")

    return "\n".join(lines)
```

## 3.5 Generate `StrEnum` for all-unit helper enums

For enums like `Transform`, `Layer`, `ColumnDisplay`, etc., generate this instead of wrapper models:

```python
class Transform(StrEnum):
    NORMAL = "Normal"
    _90 = "90"
    _180 = "180"
    _270 = "270"
```

Make sure field typing and JSON serialization still work correctly.

## 3.6 Generate `RootModel` wrappers for mixed enums

Generate:

* a union alias for the root type
* the root wrapper subclass
* `Reply.unwrap()` on `Reply`

Example target for `Action`:

```python
ActionValue = (
    CenterColumnAction
    | CloseOverviewAction
    | FocusWindowDownAction
    | ToggleOverviewAction
    # ...
)

class Action(ExternallyTaggedEnum[ActionValue]):
    __niri_variants__ = (
        CenterColumnAction,
        CloseOverviewAction,
        FocusWindowDownAction,
        ToggleOverviewAction,
        # ...
    )
```

Example target for `Event`:

```python
EventValue = (
    ConfigLoadedEvent
    | KeyboardLayoutsChangedEvent
    | WorkspacesChangedEvent
    | UnknownEvent
)

class Event(ExternallyTaggedEnum[EventValue]):
    __niri_variants__ = (
        ConfigLoadedEvent,
        KeyboardLayoutsChangedEvent,
        WorkspacesChangedEvent,
    )
    __niri_unknown_variant_model__ = UnknownEvent
```

## 3.7 Generate `Reply.unwrap()`

Generate it directly in `reply.py`:

```python
class Reply(ExternallyTaggedEnum[ReplyValue]):
    __niri_variants__ = (
        ErrReply,
        OkReply,
    )

    def unwrap(self) -> ResponseValue:
        if isinstance(self.root, OkReply):
            return self.root.payload.root

        if isinstance(self.root, ErrReply):
            raise RemoteError(
                f"Compositor error: {self.root.payload}",
                operation="Reply.unwrap",
                remote_message=self.root.payload,
            )

        raise DecodeError(
            f"Unexpected reply variant: {type(self.root).__name__}",
            operation="Reply.unwrap",
        )
```

## 3.8 Do not generate `UnknownReply`

Delete that concept entirely.

Unknown replies should fail fast.

## 3.9 Update imports in generated modules

Generated files should import from:

* `niri_pypc.types.base`
* other generated modules
* `enum.StrEnum` when needed

Stop importing:

* `BaseModel`
* `ConfigDict`
* `model_validator`
* `model_serializer`

unless a generated file truly needs them beyond inheritance.

## 3.10 Regenerate everything

Run:

```bash
python tools/generate_types.py
```

Then inspect representative outputs:

* `src/niri_pypc/types/generated/request.py`
* `src/niri_pypc/types/generated/reply.py`
* `src/niri_pypc/types/generated/event.py`
* `src/niri_pypc/types/generated/action.py`
* `src/niri_pypc/types/generated/models.py`

### Acceptance criteria

* `ToggleOverviewAction` carries `__niri_variant_kind__ = "struct"`.
* `VersionRequest` carries `__niri_variant_kind__ = "unit"`.
* `ErrReply` carries `__niri_variant_kind__ = "newtype"`.
* `Action`, `Request`, `Reply`, `Response`, `Event` are `RootModel` wrappers.
* all-unit helper enums are `StrEnum`s.
* `UnknownReply` no longer exists.

---

# Phase 4 — Strengthen generator verification

## Files to update

* `tools/verify_generated.py`
* add a new test file under `tests/types/`

## Goal

Verification should check semantic invariants, not just file diffs.

## 4.1 Keep diff-based verification

Do not remove the current fresh-generation diff check.

## 4.2 Add semantic checks in tests

Create:

* `tests/types/test_generated_contract.py`

Add checks like:

```python
from pydantic import RootModel
from niri_pypc.types.base import ProtocolVariant
from niri_pypc.types.generated.action import ToggleOverviewAction, Action
from niri_pypc.types.generated.request import VersionRequest
from niri_pypc.types.generated.reply import ErrReply
from niri_pypc.types.generated.models import Transform

def test_toggle_overview_is_struct_variant():
    assert issubclass(ToggleOverviewAction, ProtocolVariant)
    assert ToggleOverviewAction.__niri_wire_name__ == "ToggleOverview"
    assert ToggleOverviewAction.__niri_variant_kind__ == "struct"

def test_version_request_is_unit_variant():
    assert VersionRequest.__niri_variant_kind__ == "unit"

def test_err_reply_is_newtype_variant():
    assert ErrReply.__niri_variant_kind__ == "newtype"

def test_action_is_root_model():
    assert issubclass(Action, RootModel)

def test_transform_is_str_enum():
    assert Transform.NORMAL.value == "Normal"
```

### Acceptance criteria

* Regeneration diffs are still enforced.
* Semantic invariants are test-covered.

---

# Phase 5 — Simplify transport edges

## Files to update

* `src/niri_pypc/api/client.py`
* `src/niri_pypc/api/event_stream.py`
* optionally delete or drastically simplify `src/niri_pypc/transport/framing.py`

## Goal

Pydantic owns JSON validation and serialization. Transport owns bytes and framing only.

## 5.1 Remove JSON parsing from `framing.py`

Best end state: delete `framing.py` entirely.

If you keep it, it should only contain something like:

```python
def append_newline(payload: bytes) -> bytes:
    return payload + b"\n"
```

No `json.dumps`, no `json.loads`.

## 5.2 Refactor `NiriClient.request()`

Target behavior:

* accept a request variant directly,
* internally wrap with `Request(root=req)`,
* serialize with `model_dump_json()`,
* append newline,
* parse reply with `Reply.model_validate_json(raw)`,
* return `reply.unwrap()`.

Use this shape:

```python
from __future__ import annotations

from typing import Any

from niri_pypc.config import NiriConfig
from niri_pypc.errors import LifecycleError
from niri_pypc.transport.connection import DEFAULT_STREAM_LIMIT, UnixConnection
from niri_pypc.types.generated.reply import Reply, ResponseValue
from niri_pypc.types.generated.request import Request, RequestValue


class NiriClient:
    # ...

    async def request(self, req: RequestValue, *, timeout: float | None = None) -> ResponseValue:
        if self._closed:
            raise LifecycleError(
                "Client is closed",
                operation="request",
                state="closed",
            )

        socket_path = self._config.resolve_socket_path()
        read_timeout = timeout if timeout is not None else self._config.request_timeout

        conn = await UnixConnection.connect(
            socket_path,
            timeout=self._config.connect_timeout,
            stream_limit=max(self._config.max_frame_size + 1, DEFAULT_STREAM_LIMIT),
        )
        try:
            outbound = Request(root=req).model_dump_json().encode("utf-8") + b"\n"
            await conn.write_frame(outbound)

            raw = await conn.read_frame(
                max_size=self._config.max_frame_size,
                timeout=read_timeout,
            )
            reply = Reply.model_validate_json(raw)
            return reply.unwrap()
        finally:
            await conn.close()
```

## 5.3 Update client tests

`tests/api/test_client.py` must now expect:

* `await client.request(VersionRequest())` returns `VersionResponse`, not `Response`
* `result.payload == "0.1.0"`

Also add an action-serialization test:

```python
async def test_toggle_overview_serializes_as_zero_field_struct(mock_server):
    socket_path, ctrl = mock_server
    ctrl["response"] = b'{"Ok":{"Handled":{}}}\n'

    config = NiriConfig(socket_path=socket_path)
    async with NiriClient.connect(config) as client:
        from niri_pypc.types.generated.action import Action, ToggleOverviewAction
        from niri_pypc.types.generated.request import ActionRequest

        await client.request(ActionRequest(payload=Action(root=ToggleOverviewAction())))

    assert ctrl["received_requests"][0] == b'{"Action":{"ToggleOverview":{}}}\n'
```

### Acceptance criteria

* Client path never calls `json.loads()` or `json.dumps()`.
* Request returns response variant objects directly.
* Action wire shape is correct.

---

# Phase 6 — Make event stream bootstrap explicit

## File to rewrite

* `src/niri_pypc/api/event_stream.py`

## Goal

Handshake must be explicit and validated before event reading starts.

## 6.1 Add `_bootstrap()`

Add an internal method that:

1. sends `EventStream`
2. reads exactly one frame
3. validates it as `Reply`
4. unwraps it
5. requires `HandledResponse`
6. only then allows the stream to become ready

Use this shape:

```python
from niri_pypc.errors import ProtocolError
from niri_pypc.types.generated.reply import HandledResponse, Reply
from niri_pypc.types.generated.request import EventStreamRequest, Request

async def _bootstrap(self, conn: UnixConnection) -> None:
    outbound = Request(root=EventStreamRequest()).model_dump_json().encode("utf-8") + b"\n"
    await conn.write_frame(outbound)

    raw = await conn.read_frame(
        max_size=self._config.max_frame_size,
        timeout=self._config.request_timeout,
    )
    reply = Reply.model_validate_json(raw)
    response = reply.unwrap()

    if not isinstance(response, HandledResponse):
        raise ProtocolError(
            f"EventStream bootstrap expected HandledResponse, got {type(response).__name__}",
            operation="event_stream_bootstrap",
        )
```

## 6.2 Update `connect()`

New order:

```python
instance._connection = conn
await instance._bootstrap(conn)
instance._queue = asyncio.Queue(...)
instance._reader_task = asyncio.create_task(instance._run_reader())
await mgr.transition_to(LifecycleState.READY)
return instance
```

## 6.3 Update `_run_reader()`

Reader should only decode `Event`:

```python
event = Event.model_validate_json(raw)
item = _EventItem(event=event.root)
```

## 6.4 Add handshake tests

Rewrite `tests/api/test_event_stream.py` so the fake server sends:

1. `{"Ok":{"Handled":{}}}`
2. then events

Add tests for:

* handshake success
* handshake `Err` -> `RemoteError`
* handshake wrong reply type -> `ProtocolError`
* first yielded item is always an event, never a reply
* no `UnknownEvent("Ok")` bootstrap artifact

Example:

```python
async def test_stream_consumes_handshake_before_first_event(event_server):
    socket_path, ctrl = event_server
    ctrl["bootstrap_reply"] = {"Ok": {"Handled": {}}}
    ctrl["events"] = [{"WorkspaceActivated": {"id": 1, "focused": True}}]

    stream = await NiriEventStream.connect(NiriConfig(socket_path=socket_path))
    event = await stream.next(timeout=1.0)

    assert event.id == 1
    assert event.focused is True
```

### Acceptance criteria

* Stream never misclassifies bootstrap reply as event.
* `READY` means the stream is actually bootstrapped.

---

# Phase 7 — Rewrite fake socket helpers and fixtures

## Files to update

* `tests/helpers/fake_niri_socket.py`
* `tests/api/test_event_stream.py`
* `tests/conftest.py`
* `tests/api/test_bundle.py`

## Goal

Test fixtures must reflect the actual protocol.

## 7.1 Change event server helpers

Event servers must accept a separate bootstrap reply.

Refactor config:

```python
@dataclass
class FakeSocketConfig:
    response: bytes | None = None
    bootstrap_reply: dict | None = None
    events: list[dict] = field(default_factory=list)
    received_requests: list[bytes] = field(default_factory=list)
    received_request: bytes | None = None
```

Then event server handler should do:

```python
if config.bootstrap_reply is not None:
    writer.write(json.dumps(config.bootstrap_reply).encode() + b"\n")
    await writer.drain()

for evt in config.events:
    writer.write(json.dumps(evt).encode() + b"\n")
    await writer.drain()
```

## 7.2 Update bundle tests

Bundle event connections must also bootstrap with `Handled`.

## 7.3 Add negative fixture cases

Add explicit fixture-driven tests for:

* missing bootstrap reply
* bootstrap remote error
* malformed bootstrap JSON
* stream EOF before handshake completes

### Acceptance criteria

* No fixture streams events immediately after `EventStream`.
* Handshake failures are testable.

---

# Phase 8 — Update all generated-type tests to the new contract

## Files to rewrite

* `tests/types/test_roundtrip.py`
* `tests/types/test_reply_roundtrip.py`
* `tests/types/test_unknown_variants.py`
* `tests/types/test_generated_shapes.py`

## Goal

Tests must verify the new architecture, not the old `.variant` wrapper pattern.

## 8.1 Update round-trip tests to `RootModel`

Old:

```python
req = VersionRequest()
encoded = Request(variant=req).model_dump(mode="json")
assert isinstance(decoded.variant, VersionRequest)
```

New:

```python
req = VersionRequest()
encoded = Request(root=req).model_dump(mode="json")
assert encoded == "Version"

decoded = Request.model_validate("Version")
assert isinstance(decoded.root, VersionRequest)
```

## 8.2 Add unit vs zero-field-struct distinction

This is mandatory.

```python
def test_unit_variant_uses_string_form():
    encoded = Request(root=VersionRequest()).model_dump(mode="json")
    assert encoded == "Version"

def test_zero_field_struct_action_uses_object_form():
    from niri_pypc.types.generated.action import Action, ToggleOverviewAction

    encoded = Action(root=ToggleOverviewAction()).model_dump(mode="json")
    assert encoded == {"ToggleOverview": {}}

def test_newtype_uses_tagged_scalar_form():
    from niri_pypc.types.generated.reply import ErrReply, Reply

    encoded = Reply(root=ErrReply(payload="boom")).model_dump(mode="json")
    assert encoded == {"Err": "boom"}
```

## 8.3 Remove `UnknownReply` tests

Delete them entirely.

Keep only `UnknownEvent` tests.

## 8.4 Add `Reply.unwrap()` tests

Create assertions like:

```python
def test_reply_unwrap_returns_response_variant():
    from niri_pypc.types.generated.reply import Reply, VersionResponse

    reply = Reply.model_validate({"Ok": {"Version": "25.11"}})
    result = reply.unwrap()
    assert isinstance(result, VersionResponse)
    assert result.payload == "25.11"
```

### Acceptance criteria

* No `.variant` assertions remain in type contract tests.
* Unknown reply behavior is gone.
* Zero-field-struct wire shape is explicitly protected.

---

# Phase 9 — Update all runtime and integration tests to the new public shape

## Files to touch

* `tests/api/test_client.py`
* `tests/api/test_bundle.py`
* `tests/integration/test_command_flow.py`
* `tests/integration/test_independence.py`
* `tests/integration/test_nested_niri_basic.py`
* `tests/integration/test_nested_niri_events.py`
* `tests/live/test_live.py`
* any other file that still uses `.variant`

## Goal

Client now returns response variants directly.

## 9.1 Replace `.variant.payload` usages

Old:

```python
result = await client.request(VersionRequest())
assert result.variant.payload == "0.1.0"
```

New:

```python
result = await client.request(VersionRequest())
assert result.payload == "0.1.0"
```

## 9.2 Replace wrapper construction

Old:

```python
Request(variant=VersionRequest())
Action(variant=ToggleOverviewAction())
```

New:

```python
Request(root=VersionRequest())
Action(root=ToggleOverviewAction())
```

## 9.3 Run grep repeatedly

Use:

```bash
rg -n '\.variant|variant=' src tests demo
```

This should trend toward zero.

### Acceptance criteria

* Runtime tests no longer rely on `.variant`.
* Integration and live tests compile and run with the new public shape.

---

# Phase 10 — Refactor the demo

## File to update

* `demo/visual_demo.py`

## Goal

Demo should reflect the new architecture and become more deterministic.

## 10.1 Stop treating `client.request()` as returning a wrapper

Update helpers.

Old:

```python
response = await client.request(request)
return getattr(response.variant, "payload", None)
```

New:

```python
response = await client.request(request)
return getattr(response, "payload", None)
```

Update `_request_typed()` similarly:

```python
async def _request_typed[TResponse](
    client: NiriClient,
    request: BaseModel,
    expected: type[TResponse],
    state: DemoState | None = None,
) -> TResponse:
    _wire_log(state, "out", type(request).__name__, request.model_dump(mode="json"))
    response = await client.request(request)
    _wire_log(state, "in", type(response).__name__, response.model_dump(mode="json"))
    if not isinstance(response, expected):
        raise TypeError(f"Expected {expected.__name__}, got {type(response).__name__}")
    return response
```

## 10.2 Keep `Action` wrapper explicit in nested action payloads

Use:

```python
await _send_action(
    client,
    Action(root=ToggleOverviewAction()),
    state,
)
```

## 10.3 Replace toggle choreography with explicit overview actions

Prefer:

* `OpenOverviewAction()`
* `CloseOverviewAction()`

not toggle twice.

## 10.4 Reduce blind sleeps

Add helpers like:

```python
async def wait_for_window_count(client: NiriClient, expected_min: int, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        response = await client.request(WindowsRequest())
        if len(response.payload) >= expected_min:
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("window count did not reach expected value")
        await asyncio.sleep(0.05)
```

Use similar helpers for:

* overview open/closed
* workspace focus
* window count

### Acceptance criteria

* Demo no longer references `.variant`.
* Demo does not log handshake reply as unknown event.
* Demo no longer produces parser errors for zero-field struct actions.

---

# Phase 11 — Refactor the nested harness

## File to update

* `tests/helpers/nested_niri.py`

## Goal

Harness readiness should mean protocol is alive, not just socket exists.

## 11.1 Make fixture models strict and frozen

Use a shared local base:

```python
from pydantic import BaseModel, ConfigDict, Field

class FixtureModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
    )
```

Then:

```python
class ScenarioRuntime(FixtureModel):
    startup_timeout_s: float = 15.0
    ready_probe_interval_s: float = 0.1
    settle_delay_s: float = 0.25
    event_timeout_s: float = 3.0
```

Do the same for:

* `ScenarioCapabilities`
* `ScenarioExpectations`
* `NestedNiriScenario`

## 11.2 Add protocol readiness probe

After socket discovery, probe the IPC with `VersionRequest`.

Add helper:

```python
async def _wait_until_protocol_ready(
    self,
    socket_path: Path,
    timeout_s: float,
    interval_s: float,
) -> None:
    from niri_pypc import NiriClient, NiriConfig
    from niri_pypc.types.generated.request import VersionRequest

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            config = NiriConfig(socket_path=socket_path, connect_timeout=interval_s, request_timeout=interval_s)
            async with NiriClient.connect(config) as client:
                response = await client.request(VersionRequest())
                if response.payload:
                    return
        except Exception:
            await asyncio.sleep(interval_s)

    raise RuntimeError(f"IPC did not become ready for socket {socket_path}")
```

Call this before declaring the instance started.

## 11.3 Keep `settle_delay_s` only as optional polish

It should no longer define correctness.

### Acceptance criteria

* Manifest models are strict.
* Harness startup is based on real protocol readiness.

---

# Phase 12 — Rewrite harness tests

## Files to update

* `tests/helpers/test_nested_niri_hardening.py`
* relevant nested integration tests

## Add tests for

* malformed scenario YAML rejected because of `extra="forbid"`
* missing config fixture still rejected
* readiness probe retries until protocol comes up
* readiness probe fails cleanly when socket exists but protocol is dead

Example:

```python
@pytest.mark.asyncio
async def test_wait_until_protocol_ready_retries_then_succeeds(tmp_path: Path):
    # Use monkeypatch or a fake client helper to simulate two failures then success.
    ...
```

### Acceptance criteria

* Harness tests cover protocol-readiness semantics, not just socket appearance.

---

# Phase 13 — Remove dead architecture and old assumptions

## Files to clean

* `src/niri_pypc/types/codec.py`
* `src/niri_pypc/types/__init__.py`
* `src/niri_pypc/transport/framing.py` if still present
* README/demo/docs/examples
* comments in tests and helpers

## Delete or update

* `unwrap_reply()` helper
* any reference to `.variant`
* any doc saying wrappers are ordinary `BaseModel`s with a `.variant` field
* any fake event stream fixture that starts streaming before ack
* any test comments that describe the old behavior as intended

---

# Phase 14 — Final verification checklist

Run all of these before calling the refactor complete:

```bash
python tools/generate_types.py
python tools/verify_generated.py
ruff check .
ruff format --check .
pytest -q
```

Then run the visible demo again:

```bash
NIRI_PYPC_ALLOW_VISIBLE_NESTED=1 python demo/visual_demo.py --wire-log
```

## Expected demo outcomes

You should verify all of the following:

* the first stream bootstrap reply is consumed internally and does **not** appear as `UnknownEvent`,
* zero-field struct actions such as `ToggleOverview`, `FocusWindowDown`, `MoveWindowDown`, `MoveColumnLeft`, etc. serialize as object-tagged empty payloads,
* those actions stop producing compositor parser errors,
* command requests still succeed,
* event stream still delivers normal events,
* demo remains stable and teardown is clean.

---

# Concrete end-state examples

These are the kinds of generated models we want to end up with.

## `request.py`

```python
from __future__ import annotations

from typing import TypeAlias

from niri_pypc.types.base import ExternallyTaggedEnum, ProtocolVariant
from niri_pypc.types.generated.action import Action
from niri_pypc.types.generated.models import OutputAction


class EventStreamRequest(ProtocolVariant):
    __niri_wire_name__ = "EventStream"
    __niri_variant_kind__ = "unit"


class VersionRequest(ProtocolVariant):
    __niri_wire_name__ = "Version"
    __niri_variant_kind__ = "unit"


class OutputRequest(ProtocolVariant):
    __niri_wire_name__ = "Output"
    __niri_variant_kind__ = "struct"

    action: OutputAction
    output: str


RequestValue: TypeAlias = EventStreamRequest | VersionRequest | OutputRequest  # etc.


class Request(ExternallyTaggedEnum[RequestValue]):
    __niri_variants__ = (
        EventStreamRequest,
        VersionRequest,
        OutputRequest,
        # ...
    )
```

## `action.py`

```python
from __future__ import annotations

from typing import TypeAlias

from niri_pypc.types.base import ExternallyTaggedEnum, ProtocolVariant


class ToggleOverviewAction(ProtocolVariant):
    __niri_wire_name__ = "ToggleOverview"
    __niri_variant_kind__ = "struct"


class MoveWindowToWorkspaceDownAction(ProtocolVariant):
    __niri_wire_name__ = "MoveWindowToWorkspaceDown"
    __niri_variant_kind__ = "struct"

    focus: bool


ActionValue: TypeAlias = ToggleOverviewAction | MoveWindowToWorkspaceDownAction  # etc.


class Action(ExternallyTaggedEnum[ActionValue]):
    __niri_variants__ = (
        ToggleOverviewAction,
        MoveWindowToWorkspaceDownAction,
        # ...
    )
```

## `reply.py`

```python
from __future__ import annotations

from typing import TypeAlias

from niri_pypc.errors import DecodeError, RemoteError
from niri_pypc.types.base import ExternallyTaggedEnum, ProtocolVariant


class ErrReply(ProtocolVariant):
    __niri_wire_name__ = "Err"
    __niri_variant_kind__ = "newtype"

    payload: str


class OkReply(ProtocolVariant):
    __niri_wire_name__ = "Ok"
    __niri_variant_kind__ = "newtype"

    payload: Response


ReplyValue: TypeAlias = ErrReply | OkReply


class Reply(ExternallyTaggedEnum[ReplyValue]):
    __niri_variants__ = (ErrReply, OkReply)

    def unwrap(self) -> ResponseValue:
        if isinstance(self.root, OkReply):
            return self.root.payload.root
        if isinstance(self.root, ErrReply):
            raise RemoteError(
                f"Compositor error: {self.root.payload}",
                operation="Reply.unwrap",
                remote_message=self.root.payload,
            )
        raise DecodeError(
            f"Unexpected reply variant: {type(self.root).__name__}",
            operation="Reply.unwrap",
        )
```

## `models.py` for a unit-only helper enum

```python
from enum import StrEnum


class Transform(StrEnum):
    NORMAL = "Normal"
    _90 = "90"
    _180 = "180"
    _270 = "270"
```

---

# Minimum required test matrix

These tests are not optional.

## Types / codec

* unit variant encodes to string
* zero-field struct encodes to `{Tag: {}}`
* newtype encodes to `{Tag: payload}`
* wrong wire shape raises `DecodeError`
* unknown event returns `UnknownEvent`
* unknown reply raises decode/protocol failure

## Client

* `VersionRequest` sends `"Version"`
* `ActionRequest(payload=Action(root=ToggleOverviewAction()))` sends `{"Action":{"ToggleOverview":{}}}`
* `Err` reply raises `RemoteError`
* `request()` returns response variant directly

## Event stream

* bootstrap reply is consumed before any yielded event
* bootstrap `Err` raises `RemoteError`
* bootstrap wrong reply shape raises `ProtocolError`
* reader only yields event payload models
* unknown future event yields `UnknownEvent`
* queue/backpressure behavior still works

## Generator contract

* representative variants preserve IR kind
* representative wrappers are `RootModel`s
* representative all-unit enums become `StrEnum`
* `UnknownReply` is absent
* generated output matches generator

## Harness

* scenario manifests reject extra keys
* readiness requires protocol success, not just socket existence

## Demo / integration

* demo runs without bootstrap misclassification
* previously failing zero-field struct actions no longer produce parser errors
* visible nested run still tears down cleanly

---

# What I would tell the agent explicitly

1. Do the generator and handwritten runtime together.
2. Do not preserve old `.variant` APIs.
3. Do not patch generated files manually and move on.
4. Delete wrong tests as soon as the new contract exists.
5. Keep the refactor cohesive: types, codec, transport, stream bootstrap, fixtures, demo, and harness all move together.
6. The most important invariant is this:

> **variant kind is explicit and authoritative**
>
> The runtime must never infer wire semantics from Python field shape again.

If you want, I can turn this into an even more implementation-oriented checklist with exact per-file edit order and a suggested sequence of commits.
