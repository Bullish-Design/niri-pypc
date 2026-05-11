# REFACTORING OPPORTUNITIES — niri-pypc

**Author:** Deep code review analysis  
**Date:** 2026-05-11  
**Scope:** Full refactoring roadmap for a brand-new library with zero users. Backwards compatibility is explicitly not a constraint.

---

## Table of Contents

1. [Adopt Pydantic v2 Native Discriminated Unions](#1-adopt-pydantic-v2-native-discriminated-unions)
2. [Make `UnixConnection` an Async Context Manager](#2-make-unixconnection-an-async-context-manager)
3. [Fix the Error Taxonomy Properly](#3-fix-the-error-taxonomy-properly)
4. [Simplify `NiriClient` — Drop the LifecycleManager](#4-simplify-niriclient--drop-the-lifecyclemanager)
5. [Redesign `NiriEventStream` Close Path](#5-redesign-nirieventstream-close-path)
6. [Fix `NiriConnectionBundle` State Hack](#6-fix-niriconnectionbundle-state-hack)
7. [Upgrade the Generator to Produce Cleaner Output](#7-upgrade-the-generator-to-produce-cleaner-output)
8. [Add `__all__` to Public Modules](#8-add-all-to-public-modules)
9. [Remove Unnecessary Lazy Import in `config.py`](#9-remove-unnecessary-lazy-import-in-configpy)
10. [Improve Test Architecture](#10-improve-test-architecture)
11. [Make `encode_frame` Resilient](#11-make-encode_frame-resilient)
12. [Add Runtime Schema Hash Verification](#12-add-runtime-schema-hash-verification)
13. [Consider a `NiriClient` Connection Pool](#13-consider-a-niriclient-connection-pool)
14. [Priority Matrix](#14-priority-matrix)

---

## 1. Adopt Pydantic v2 Native Discriminated Unions

### Current Pattern

Every generated enum model (Request, Reply, Event, Action, and ~15 helper enums) follows this boilerplate:

```python
# Wire-name to variant class mapping
_REQUEST_VARIANTS: dict[str, type[BaseModel]] = {
    "Action": ActionRequest,
    "EventStream": EventStreamRequest,
    ...
}

# Variant class to wire-name mapping
_REQUEST_VARIANT_NAMES: dict[type[BaseModel], str] = {
    ActionRequest: "Action",
    EventStreamRequest: "EventStream",
    ...
}

class Request(BaseModel):
    model_config = ConfigDict(populate_by_name=True, strict=False)
    variant: ActionRequest | EventStreamRequest | ...

    @model_validator(mode="before")
    @classmethod
    def _decode_external_tag(cls, data: Any) -> dict[str, Any]:
        from niri_pypc.types.codec import decode_externally_tagged
        if isinstance(data, dict) and "variant" in data and isinstance(data["variant"], BaseModel):
            return data
        return {"variant": decode_externally_tagged(data, _REQUEST_VARIANTS)}

    @model_serializer
    def _encode_external_tag(self) -> Any:
        from niri_pypc.types.codec import encode_externally_tagged
        return encode_externally_tagged(self.variant, _REQUEST_VARIANT_NAMES)
```

This pattern is repeated identically across 19 enum models (4 top-level + 15 helper). The boilerplate alone accounts for ~200 lines of generated code.

### Proposed Pattern Using Pydantic `Discriminator`

Pydantic v2.10+ supports `Annotated` with `Field(discriminator=...)` for externally-tagged unions:

```python
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, Field

class ActionRequest(BaseModel):
    payload: Action

class EventStreamRequest(BaseModel):
    pass

class VersionRequest(BaseModel):
    pass

# The "tag" is the literal field name in the wire JSON
RequestVariant = Annotated[
    ActionRequest | EventStreamRequest | VersionRequest | ...,
    Field(discriminator=Literal["Action", "EventStream", "Version", ...])
]

# Or using a custom discriminator function:
def request_discriminator(v):
    if isinstance(v, str):
        return v  # unit variant — the string IS the variant name
    if isinstance(v, dict):
        return next(iter(v.keys()))  # dict variant — key is the name
    return None

RequestVariant = Annotated[
    ActionRequest | EventStreamRequest | ...,
    Field(discriminator=request_discriminator)
]
```

**However**, there is a significant complication: Pydantic's built-in discriminated union support expects the discriminator key to be a *field name within the payload dict*, not the top-level key wrapping the entire payload. For externally-tagged enums (where `{"Action": {...}}` is the top-level structure), we still need a custom `model_validator` approach — but it can be simplified.

### More Realistic Refactor: Template the Boilerplate

Rather than fighting Pydantic's discriminator API (which doesn't natively support the serde-style external tagging), the pragmatic refactor is to **template the boilerplate** more aggressively:

```python
# In the generator, define a template once:
ENUM_TEMPLATE = """\
class {enum_name}(BaseModel):
    model_config = ConfigDict(populate_by_name=True, strict=False)
    variant: {union_str}

    @model_validator(mode="before")
    @classmethod
    def _decode_external_tag(cls, data: Any) -> dict[str, Any]:
        from niri_pypc.types.codec import decode_externally_tagged
        if isinstance(data, dict) and "variant" in data and isinstance(data["variant"], BaseModel):
            return data
        return {{"variant": decode_externally_tagged(
            data, {variants_dict}, {sentinel_arg}
        )}}

    @model_serializer
    def _encode_external_tag(self) -> Any:
        from niri_pypc.types.codec import encode_externally_tagged
        return encode_externally_tagged(self.variant, {names_dict})
"""
```

This wouldn't change runtime behavior but would make the generator code a single source of truth for the template, reducing generated-file maintenance burden.

### Justification

- **Eliminates ~200 lines of repetitive code** across 19 enum models
- **Reduces diff noise** when the generator changes
- **Single point of change** if the decoding/encoding pattern needs updating
- If Pydantic eventually supports serde-style external tagging natively, only the template changes

### Effort: Medium (1-2 days)

---

## 2. Make `UnixConnection` an Async Context Manager

### Current Code

```python
# src/niri_pypc/transport/connection.py
class UnixConnection:
    def __init__(self, reader, writer, socket_path):
        ...
    
    @classmethod
    async def connect(cls, socket_path, *, timeout=5.0):
        reader, writer = await asyncio.wait_for(...)
        return cls(reader, writer, socket_path)
    
    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        ...
```

Users must remember the `try/finally` pattern:

```python
conn = await UnixConnection.connect(path)
try:
    await conn.write_frame(frame)
    response = await conn.read_frame(timeout=5.0)
finally:
    await conn.close()
```

### Proposed Change

Add `__aenter__` and `__aexit__`:

```python
class UnixConnection:
    ...
    
    async def __aenter__(self) -> UnixConnection:
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
```

This enables:

```python
async with UnixConnection.connect(path, timeout=5.0) as conn:
    await conn.write_frame(frame)
    response = await conn.read_frame(timeout=5.0)
```

### Downstream Impact

`NiriClient.request()` currently does:

```python
conn = await UnixConnection.connect(socket_path, timeout=self._config.connect_timeout)
try:
    ...
finally:
    await conn.close()
```

This simplifies to:

```python
async with UnixConnection.connect(socket_path, timeout=self._config.connect_timeout) as conn:
    ...
```

### Justification

- **Eliminates a common footgun** — forgetting to close the connection in an error path
- **Aligns with Python stdlib conventions** — `asyncio.open_unix_connection()` already supports `async with`
- **Simplifies the most common usage pattern** across all API methods
- **Makes `NiriClient.request()` read more linearly** — the `try/finally` nesting is removed

### Effort: Low (30 minutes)

---

## 3. Fix the Error Taxonomy Properly

### Problem 1: `unwrap_reply` Uses Name-Prefix Matching

```python
# Current: src/niri_pypc/types/codec.py:141-151
cls_name = type(variant).__name__
if cls_name.startswith("Ok"):
    return getattr(variant, "payload", variant)
if cls_name.startswith("Err"):
    msg = getattr(variant, "payload", str(variant))
```

This is fragile. If anyone adds a variant starting with "Ok" or "Err" to any model, it silently misbehaves.

**Proposed fix — use the generated dispatch maps:**

The generated `reply.py` already contains `_REPLY_VARIANTS` and `_REPLY_VARIANT_NAMES`. We can import and use them:

```python
from niri_pypc.types.generated.reply import _REPLY_VARIANTS, OkReply, ErrReply

def unwrap_reply(reply: Reply) -> Any:
    variant = getattr(reply, "variant", None)
    if variant is None:
        raise DecodeError("Reply missing variant field", operation="unwrap_reply")
    
    if isinstance(variant, OkReply):
        return getattr(variant, "payload", variant)
    if isinstance(variant, ErrReply):
        msg = getattr(variant, "payload", str(variant))
        raise RemoteError(
            f"Compositor error: {msg}",
            operation="unwrap_reply",
            remote_message=str(msg),
        )
    
    raise DecodeError(f"Unexpected reply variant: {type(variant).__name__}", operation="unwrap_reply")
```

This is **exhaustively type-checkable** — if the Reply variants change, the type checker will flag the missing `isinstance` branch.

### Problem 2: `EncodeError` Doesn't Exist

The spec (Section 8) mentions `EncodeError` as a subclass of `NiriError`, but it doesn't exist. `encode_externally_tagged` raises `DecodeError` for unknown outbound variants, which is semantically wrong:

```python
# Current: raises DecodeError for an encoding problem
raise DecodeError(
    f"Unknown variant class: {cls.__name__}",
    operation="encode_externally_tagged",
)
```

**Proposed fix — add `EncodeError` to the taxonomy:**

```python
class EncodeError(NiriError):
    """Failed to encode a variant into wire format."""
```

And use it in `encode_externally_tagged`:

```python
if wire_name is None:
    raise EncodeError(
        f"Unknown variant class: {cls.__name__}",
        operation="encode_externally_tagged",
    )
```

### Problem 3: Missing `raw_payload` Truncation Enforcement

The spec says `raw_payload` should be truncated to 1024 characters. Currently this is done with `raw_payload[:1024]` inline in three places, but there's no enforcement or test. Consider adding a helper:

```python
TRUNCATE = 1024

def _truncate(value: Any) -> str:
    s = str(value)
    return s[:TRUNCATE]
```

### Justification

- **Type-safe dispatch** prevents silent misbehavior when the protocol evolves
- **Correct error semantics** — encoding failures should never masquerade as decode failures
- **Self-documenting** — `isinstance` checks make the dispatch logic obvious to readers

### Effort: Low-Medium (1 day)

---

## 4. Simplify `NiriClient` — Drop the LifecycleManager

### Current Code

```python
class NiriClient:
    def __init__(self, config):
        self._config = config
        self._lifecycle = LifecycleManager()  # Heavy machinery for...
    
    @classmethod
    async def connect(cls, config=None):
        config = config or NiriConfig()
        config.resolve_socket_path()  # validate
        return cls(config)  # ...a boolean check
    
    async def request(self, req, *, timeout=None):
        if self._lifecycle.is_terminal:  # Check once per request
            raise LifecycleError(...)
        ...
    
    async def close(self):
        if not self._lifecycle.is_terminal:
            await self._lifecycle.transition_to(LifecycleState.CLOSED)
```

The `LifecycleManager` is overkill here. `NiriClient` uses one-connection-per-request, so there's no connection state to manage — the client is either "usable" (not closed) or "closed." No intermediate states exist.

### Proposed Change

```python
class NiriClient:
    def __init__(self, config: NiriConfig) -> None:
        self._config = config
        self._closed = False
    
    @classmethod
    def connect(cls, config: NiriConfig | None = None) -> NiriClient:
        if config is None:
            config = NiriConfig()
        config.resolve_socket_path()
        return cls(config)
    
    @property
    def is_closed(self) -> bool:
        return self._closed
    
    async def request(self, req, *, timeout=None):
        if self._closed:
            raise LifecycleError(
                "Client is closed",
                operation="request",
                state="closed",
            )
        ...
    
    async def close(self) -> None:
        self._closed = True
    
    async def __aenter__(self) -> NiriClient:
        return self
    
    async def __aexit__(self, *_) -> None:
        self._closed = True
```

### Downstream Benefits

1. **Removes async lock contention** — no `async with self._lifecycle._lock` on every request
2. **Simplifies `close()`** — no async state machine transition, just a boolean assignment
3. **`is_closed` is a simple property** — no enum comparison needed
4. **Test simplification** — no need to test lifecycle transition states for the client

### Justification

- The `LifecycleManager` was designed for connection-oriented state machines (CONNECTING → READY → CLOSING) that apply to `NiriEventStream`, not to a stateless-per-request client
- A closed client is indistinguishable from an unopened one — only "not yet closed" vs "closed" matters
- This makes the `LifecycleManager` exclusively belong to `NiriEventStream` where it's genuinely needed

### Effort: Low (1-2 hours)

---

## 5. Redesign `NiriEventStream` Close Path

### Current Problem

Two independent code paths can initiate the lifecycle transition:

1. **`close()` (user-initiated):** transitions CLOSING → CLOSED, cancels reader task, closes connection
2. **`_close_from_reader()` (reader-initiated):** transitions to CLOSING → CLOSED, puts sentinel in queue

Both paths check `is_terminal` before starting, but between the check and the transition, the other path could have already started. The `asyncio.Lock` inside `transition_to` serializes the actual transitions, but the TOCTOU window on `is_terminal` remains.

Additionally, the reader's outer `except Exception: pass` (line 123) silently swallows all errors:

```python
try:
    while True:
        try:
            raw = await conn.read_frame(...)
        except TransportError:
            break
        try:
            event = Event.model_validate(decoded)
        except Exception:
            continue  # ← Silent swallowing
except Exception:
    pass  # ← Even more silent swallowing
finally:
    await self._close_from_reader()
```

### Proposed Redesign

Use an `asyncio.Event` as a shutdown signal, eliminating the dual-initiation problem:

```python
class NiriEventStream:
    def __init__(self, config: NiriConfig) -> None:
        self._config = config
        self._lifecycle = LifecycleManager()
        self._queue: asyncio.Queue[BaseModel | _StreamClosed] | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._connection: UnixConnection | None = None
        self._closing = asyncio.Event()

    async def close(self) -> None:
        if self._closing.is_set():
            return  # Idempotent
        self._closing.set()
        
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None
        
        if self._queue is not None:
            self._queue.put_nowait(_StreamClosed())
        
        if not self._lifecycle.is_terminal:
            await self._lifecycle.transition_to(LifecycleState.CLOSED)

    async def _run_reader(self) -> None:
        conn = self._connection
        queue = self._queue
        config = self._config
        if conn is None or queue is None:
            return

        while not self._closing.is_set():
            try:
                raw = await asyncio.wait_for(
                    conn.read_frame(max_size=config.max_frame_size),
                    timeout=config.event_read_timeout,
                )
            except (TransportError, TimeoutError, asyncio.CancelledError):
                break

            try:
                decoded = decode_frame(raw)
                event = Event.model_validate(decoded)
            except (DecodeError, ValidationError) as exc:
                # Log malformed events but don't crash
                logger.warning("Malformed event received: %s", exc)
                continue

            if config.backpressure_mode == BackpressureMode.DROP_OLDEST:
                try:
                    queue.put_nowait(event.variant)
                except asyncio.QueueFull:
                    try:
                        queue.get_nowait()
                        queue.put_nowait(event.variant)
                    except asyncio.QueueEmpty:
                        pass
            else:  # FAIL_FAST
                try:
                    queue.put_nowait(event.variant)
                except asyncio.QueueFull:
                    break  # Signal close via finally block
        
        # Only initiate close from reader if not already closing via user call
        if not self._closing.is_set():
            self._closing.set()
            if self._queue is not None:
                self._queue.put_nowait(_StreamClosed())
            if not self._lifecycle.is_terminal:
                await self._lifecycle.transition_to(LifecycleState.CLOSED)
```

### Key Changes

1. **Single close initiation:** `self._closing` (an `asyncio.Event`) is the single source of truth for "should we stop." Both `close()` and `_run_reader` set it, and the reader checks it each iteration.
2. **`close()` is the only path that transitions lifecycle** — the reader only sets the closing flag and puts the sentinel; `close()` does the actual transition.
3. **Better error handling** — `TransportError` and `TimeoutError` are caught specifically, not lumped with `Exception`. `DecodeError` and `ValidationError` are logged, not silently swallowed.
4. **No `_close_from_reader` helper** — reduces the number of code paths that can initiate shutdown from 2 to 1.

### Justification

- Eliminates the TOCTOU race entirely
- Cleaner separation: reader reads, caller closes
- Better observability: malformed events are logged, not silently dropped
- The `asyncio.Event` pattern is well-understood and idiomatic

### Effort: Medium (half a day)

---

## 6. Fix `NiriConnectionBundle` State Hack

### Current Code

```python
class NiriConnectionBundle:
    def __init__(self, client, events):
        self._client = client
        self._events = events
        self._lifecycle = LifecycleManager()
        self._lifecycle._state = LifecycleState.READY  # ← Internal state mutation
```

### Why This Is Bad

- Directly mutates `_state` on a `LifecycleManager`, bypassing all transition validation
- Creates an impossible-to-reproduce state (a `LifecycleManager` that starts at READY instead of INIT)
- Couples `NiriConnectionBundle` to `LifecycleManager` internals
- If `LifecycleManager` adds validation or side effects for state changes, this breaks silently

### Proposed Change — Option A: Remove Lifecycle from Bundle

The bundle is a convenience wrapper, not a stateful resource. Its members own their state:

```python
class NiriConnectionBundle:
    def __init__(self, client: NiriClient, events: NiriEventStream) -> None:
        self._client = client
        self._events = events

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed and self._events._lifecycle.is_terminal

    async def close(self) -> None:
        exc_caught = None
        try:
            await self._client.close()
        except Exception as exc:
            exc_caught = exc
        try:
            await self._events.close()
        except Exception as exc:
            if exc_caught is None:
                exc_caught = exc
        if exc_caught is not None:
            raise exc_caught
```

### Proposed Change — Option B: Allow Initial State

```python
class LifecycleManager:
    def __init__(self, initial_state: LifecycleState = LifecycleState.INIT) -> None:
        self._state = initial_state
```

Then the bundle does:

```python
self._lifecycle = LifecycleManager(initial_state=LifecycleState.READY)
```

### Justification

- Removes hidden coupling between unrelated components
- `LifecycleManager` remains a self-contained, testable state machine
- Bundles become simpler coordination wrappers without phantom state

### Effort: Low (30 minutes)

---

## 7. Upgrade the Generator to Produce Cleaner Output

### Issue: Ruff B009 — `getattr` with Constant Attribute

**Current generator output** (`tools/generate_types.py:178`):

```python
# In gen_enum_code, for newtype variants:
lines.append("    payload: {py_type}")

# Which produces this in the generated code:
@property
def payload(self) -> ...:
    return getattr(self, "payload")  # ← B009
```

Wait, that's not right. Let me re-check. The actual issue is in the generated `action.py` and similar files. Let me verify what generates the `getattr` call.

Looking at the generated code: there's no `getattr` in the generated files. The `getattr` call is in `codec.py:112`:

```python
payload = getattr(variant, "payload")
```

This is in the **hand-written** codec, not in generated code. So the fix is:

```python
payload = variant.payload
```

**But** this also needs to be reflected in the generator template. The generator should produce code that avoids `getattr`. Currently `gen_variant_code` produces:

```python
class ActionRequest(BaseModel):
    payload: Action
```

Which is fine — the `getattr` is in the hand-written `codec.py`, not generated. So fix `codec.py` directly.

### Issue: Ruff I001 — Unsorted Imports

The generated files have imports in this order:

```python
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, model_validator, model_serializer
```

Ruff's isort rules want stricter alphabetical grouping. The fix is in the generator's `write_file` function:

```python
# Current
HEADER_IMPORTS = """\
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, model_validator, model_serializer

"""
```

Should be:

```python
HEADER_IMPORTS = """\
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_serializer, model_validator
from typing import Any

"""
```

Wait, ruff wants: stdlib first, then third-party, then local. `from __future__` is special. `pydantic` and `typing` are third-party and stdlib respectively. Let me check ruff's expected order:

1. Future imports (`from __future__`)
2. Standard library (`typing`)
3. Third-party (`pydantic`)
4. Local/application

So the correct order for generated files should be:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator, model_serializer
```

The issue is that the generated files combine future, stdlib, and third-party imports without blank line separation. The generator's `HEADER_IMPORTS` template needs blank lines between groups.

### Issue: Unused Imports in `models.py`

```python
from pydantic import BaseModel, ConfigDict, model_validator, model_serializer
```

`model_validator` and `model_serializer` are not used in `models.py` (which only defines struct models). The fix is to conditionally include them only in files that contain enum root models.

### Proposed Generator Refactor

```python
def gen_struct_code(ir_type: dict) -> str:
    lines = []
    fields = ir_type.get("fields", [])
    lines.append(f"class {ir_type['name']}(BaseModel):")
    lines.append("    model_config = ConfigDict(populate_by_name=True, strict=False)")
    if fields:
        for f in fields:
            py_type = ir_type_to_python(f["type"])
            field_name = safe_field_name(f["name"])
            if f["required"]:
                lines.append(f"    {field_name}: {py_type}")
            else:
                lines.append(f"    {field_name}: {py_type} = None")
    else:
        lines.append("    pass")
    return "\n".join(lines)
```

No `model_validator` or `model_serializer` in struct code — correct.

### For enum files, keep both imports since they're used.

But split the import groups with a blank line:

```python
HEADER = """\
# AUTO-GENERATED by tools/generate_types.py -- DO NOT EDIT
# upstream: {upstream_crate} {upstream_version}
# ir_version: {ir_version}
# ir_hash: {ir_hash}

"""

ENUM_FILE_IMPORTS = """\
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_serializer, model_validator

"""

STRUCT_FILE_IMPORTS = """\
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

"""
```

### Justification

- Clean lint output on committed code — no need to auto-fix after every generation
- Maintains the "generated code is authoritative" principle
- Reduces noise in `git diff` when regenerating

### Effort: Low (2-3 hours, mostly testing)

---

## 8. Add `__all__` to Public Modules

### Current State

```python
# src/niri_pypc/__init__.py
__all__ = [
    "__version__", "BackpressureMode", "ConfigError", "DecodeError",
    "InternalError", "LifecycleError", "NiriClient", "NiriConfig",
    "NiriConnectionBundle", "NiriError", "NiriEventStream",
    "NiriTimeoutError", "ProtocolError", "RemoteError", "TransportError",
]

# src/niri_pypc/types/__init__.py
# No __all__ — wildcard import from generated pulls in everything
```

### Proposed Change

```python
# src/niri_pypc/types/__init__.py
"""Protocol types for niri IPC."""

from niri_pypc.types.codec import (
    decode_externally_tagged,
    encode_externally_tagged,
    unwrap_reply,
)
from niri_pypc.types.generated import *  # noqa: F401,F403

__all__ = [
    "decode_externally_tagged",
    "encode_externally_tagged",
    "unwrap_reply",
]
```

### Justification

- Prevents `from niri_pypc.types import *` from pulling in internal classes like `UnknownEvent`
- Makes the public API explicit and discoverable
- Aligns with Python packaging best practices

### Effort: Low (15 minutes)

---

## 9. Remove Unnecessary Lazy Import in `config.py`

### Current Code

```python
# src/niri_pypc/config.py
def resolve_socket_path(self) -> Path:
    ...
    from niri_pypc.errors import ConfigError
    raise ConfigError(...)
```

### Why It's Unnecessary

Check the import graph:
- `config.py` does not import `errors.py` at the top level
- `errors.py` does NOT import from `config.py`
- There is no circular dependency

### Proposed Change

```python
# Move to top of file
from niri_pypc.errors import ConfigError

@dataclass(frozen=True, slots=True)
class NiriConfig:
    ...
    
    def resolve_socket_path(self) -> Path:
        ...
        raise ConfigError(...)
```

### Bonus: Add Explicit Top-Level Import in `errors.py`

Since `config.py` now imports from `errors.py`, consider making the relationship cleaner by having `errors.py` not depend on anything internal:

```python
# src/niri_pypc/errors.py — this is already correct, no internal deps
```

### Justification

- Simpler code — no need for readers to wonder "why is this imported locally?"
- The perceived "circular import" was never circular
- Makes static analysis tools happier

### Effort: Low (5 minutes)

---

## 10. Improve Test Architecture

### 10a. Deduplicate Integration Conftest

**Current:** `tests/integration/conftest.py` just re-exports from `tests/conftest.py`:

```python
from tests.conftest import (
    mock_command_server,
    mock_event_server,
    mock_unified_server,
    temp_socket_path,
)
```

**Fix:** Delete `tests/integration/conftest.py` entirely. The root `conftest.py` fixtures are automatically available to all subdirectories.

### 10b. Add `tests/types/conftest.py`

The root conftest provides `temp_socket_path`, `mock_command_server`, etc. But type tests don't need sockets. Create a type-specific conftest for shared type fixtures:

```python
# tests/types/conftest.py
import pytest
from niri_pypc.types.generated.request import Request, VersionRequest
from niri_pypc.types.generated.event import Event
from niri_pypc.types.generated.reply import Reply


@pytest.fixture
def sample_request():
    return VersionRequest()


@pytest.fixture
def sample_event():
    return Event(variant=...)  # or a factory
```

### 10c. Parametrize Action/Event Roundtrip Tests

Instead of:

```python
class TestEventRoundtrip:
    def test_workspace_activated_event(self):
        raw = {"WorkspaceActivated": {"id": 1, "focused": True}}
        event = Event.model_validate(raw)
        encoded = event.model_dump(mode="json")
        assert encoded == raw
```

Write:

```python
SAMPLE_EVENTS = [
    ({"WorkspaceActivated": {"id": 1, "focused": True}},),
    ({"WindowClosed": {"id": 42}},),
    ({"ConfigLoaded": {"failed": False}},),
]


@pytest.mark.parametrize("raw", SAMPLE_EVENTS)
def test_event_roundtrip(raw):
    event = Event.model_validate(raw)
    assert event.model_dump(mode="json") == raw
```

### 10d. Add Missing test_categories

| Test File | Missing Coverage |
|-----------|-----------------|
| `test_roundtrip.py` | Struct variants with fields, all Action variants, newtype roundtrips |
| `test_edge_cases.py` | `None`/empty dict for Event and Reply, oversized nested dicts |
| `test_metadata.py` | `SCHEMA_HASHES` key count matches expected, hash format regex |
| `test_framing.py` | Oversize frame with exact boundary (1024 vs 1025 bytes) |
| `test_connection.py` | Write to closed connection, read from closed connection |
| `test_client.py` | Timeout override, concurrent requests |
| `test_event_stream.py` | Backpressure FAIL_FAST mode, reconnection after close |
| `test_bundle.py` | Close when events succeed but client fails, individual member access |
| `test_lifecycle.py` | Concurrent `transition_to` (asyncio.gather) |

### 10e. Add Narrowing Assertions in Integration Tests

```python
# Before:
result = await client.request(VersionRequest())
assert result.variant.payload == "0.1.0"

# After:
from niri_pypc.types.generated.reply import Reply, OkReply, VersionResponse
from niri_pypc.types.generated.request import VersionRequest

result = await client.request(VersionRequest())
assert isinstance(result, Reply)
assert isinstance(result.variant, OkReply)
assert isinstance(result.variant.payload, VersionResponse)
assert result.variant.payload.payload == "0.1.0"
```

### Justification

- **Deduplication** reduces maintenance burden
- **Parametrized tests** catch regressions across more types with less code
- **Missing categories** close coverage gaps identified in the review
- **Narrowing assertions** catch type narrowing bugs and serve as living documentation

### Effort: Medium (1-2 days)

---

## 11. Make `encode_frame` Resilient

### Current Code

```python
def encode_frame(data: Any) -> bytes:
    return json.dumps(data, separators=(",", ":")).encode("utf-8") + b"\n"
```

If `data` is not JSON-serializable (e.g., a custom object, `set`, `datetime`), this raises an unhandled `TypeError`.

### Proposed Change

```python
def encode_frame(data: Any) -> bytes:
    try:
        return json.dumps(data, separators=(",", ":")).encode("utf-8") + b"\n"
    except TypeError as exc:
        raise ProtocolError(
            f"Failed to serialize frame data: {exc}",
            operation="encode_frame",
        ) from exc
```

### Justification

- Failures are categorized correctly (`ProtocolError` rather than uncaught `TypeError`)
- Error message includes the operation name for debugging
- Chained exception preserves the root cause

### Effort: Low (10 minutes)

---

## 12. Add Runtime Schema Hash Verification

### Current State

The `_metadata.py` contains schema hashes, but they're only checked in CI by `verify_generated.py`. At runtime, a stale or mismatched schema file goes undetected.

### Proposed Change

Add a module-level check in `src/niri_pypc/types/generated/__init__.py`:

```python
# Runtime schema hash verification
import hashlib
import json
from pathlib import Path

__file__  # defined by Python
_generated_dir = Path(__file__).parent


def _verify_schema_hashes() -> None:
    """Verify that exported schema files match the committed hashes."""
    # Only verify when schema files are available (not in pip-installed packages)
    schema_dir = _generated_dir.parent.parent.parent / "schema" / "exported"
    if not schema_dir.is_dir():
        return  # Running from wheel — skip
    
    from niri_pypc.types.generated._metadata import SCHEMA_HASHES
    
    for name, expected_hash in SCHEMA_HASHES.items():
        schema_path = schema_dir / f"{name}.schema.json"
        if not schema_path.is_file():
            continue
        actual = "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
        if actual != expected_hash:
            import warnings
            warnings.warn(
                f"Schema hash mismatch for {name}: expected {expected_hash}, got {actual}. "
                "Run 'normalize-ir && generate-types' to update.",
                RuntimeWarning,
                stacklevel=2,
            )


_verify_schema_hashes()
```

### Justification

- Catches stale schema files immediately at import time
- Non-intrusive: uses `warnings.warn`, not raising exceptions (schema files may not exist in installed packages)
- Provides a clear remediation message

### Effort: Low (30 minutes)

---

## 13. Consider a `NiriClient` Connection Pool

### Current Model

One TCP handshake per request:

```
request(A) → connect → send → recv → close
request(B) → connect → send → recv → close
request(C) → connect → send → recv → close
```

For rapid-fire requests (e.g., batch window operations), this means N TCP handshakes.

### Proposed Model

Keep a single connection open and reuse it:

```python
class NiriClient:
    def __init__(self, config: NiriConfig) -> None:
        self._config = config
        self._closed = False
        self._connection: UnixConnection | None = None
        self._lock = asyncio.Lock()

    async def request(self, req, *, timeout=None):
        if self._closed:
            raise LifecycleError(...)
        
        async with self._lock:
            conn = self._get_or_connect()
            try:
                # Use provided timeout for read, config timeout for connect
                payload = RequestModel(variant=req).model_dump(mode="json")
                frame = encode_frame(payload)
                await conn.write_frame(frame)
                raw = await conn.read_frame(
                    max_size=self._config.max_frame_size,
                    timeout=timeout or self._config.request_timeout,
                )
                decoded = decode_frame(raw)
                reply = Reply.model_validate(decoded)
                return unwrap_reply(reply)
            except (TransportError, NiriTimeoutError):
                # Connection may be broken — close and retry
                await self._close_connection()
                raise

    def _get_or_connect(self) -> UnixConnection:
        if self._connection is None or self._connection.is_closed:
            self._connection = await UnixConnection.connect(
                self._config.resolve_socket_path(),
                timeout=self._config.connect_timeout,
            )
        return self._connection

    async def _close_connection(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None

    async def close(self) -> None:
        self._closed = True
        await self._close_connection()

    async def __aenter__(self) -> NiriClient:
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
```

### Trade-Offs

| Aspect | One-Connection-Per-Request | Connection Pool (One Connection) |
|--------|---------------------------|----------------------------------|
| Simplicity | ✅ Trivial to reason about | ⚠️ Requires lock, retry logic |
| Latency | ❌ N handshakes | ✅ 1 handshake |
| Error isolation | ✅ Failed request doesn't corrupt next | ⚠️ Broken connection affects subsequent requests |
| Server expectations | ✅ Matches `niri msg` behavior | ⚠️ Niri may close idle connections |
| Thread safety | ✅ Naturally safe | ⚠️ Requires lock |

### Recommendation

**Don't implement this yet.** The spec explicitly says "Start with one-connection-per-request to match upstream `niri msg` behavior." Niri may close idle connections or have other assumptions about request-per-connection. Revisit once real-world usage patterns are known and performance is proven to be a bottleneck.

### Effort: Deferred

---

## 14. Priority Matrix

### Immediate (Do on Day 1)

| # | Item | Impact | Effort |
|---|------|--------|--------|
| 3 | Add `EncodeError` to taxonomy | Correctness | Low |
| 3 | Fix `unwrap_reply` dispatch to use isinstance | Correctness | Low |
| 11 | Wrap `encode_frame` errors properly | Correctness | Low |
| 9 | Remove unnecessary lazy import | Cleanliness | Trivial |
| 8 | Add `__all__` to modules | Cleanliness | Trivial |
| 6 | Fix Bundle state hack | Design quality | Low |
| 2 | `UnixConnection.__aenter__`/`__aexit__` | Usability | Low |
| 4 | Simplify `NiriClient` (drop LifecycleManager) | Simplicity | Low |

### Short-Term (Do in First Week)

| # | Item | Impact | Effort |
|---|------|--------|--------|
| 5 | Redesign event stream close path | Correctness | Medium |
| 10a | Deduplicate conftest | Maintainability | Trivial |
| 10b-c | Parametrize type tests, add missing categories | Coverage | Medium |
| 7 | Fix generator lint issues | CI cleanliness | Low |

### Medium-Term (Do in First Month)

| # | Item | Impact | Effort |
|---|------|--------|--------|
| 12 | Runtime schema hash verification | Robustness | Low |
| 10d-e | Missing test categories and narrowing assertions | Quality | Medium |
| 1 | Templated enum boilerplate reduction | Maintainability | Medium |

### Deferred (Revisit When Needed)

| # | Item | Impact | Effort |
|---|------|--------|--------|
| 13 | Connection pool | Performance | Medium |

---

*All timings are estimates for a single developer familiar with the codebase. Actual effort may vary based on test infrastructure setup.*