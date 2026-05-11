# REFACTORING OPPORTUNITIES — niri-pypc v2.5

**Date:** 2026-05-11  
**Scope:** Full codebase review for elegance improvements  
**Note:** Backwards compatibility NOT a concern — this is a brand new library with zero users.

---

## Table of Contents

1. [Philosophy](#1-philosophy)
2. [High-Impact Refactorings](#2-high-impact-refactorings)
3. [Architectural Improvements](#3-architectural-improvements)
4. [Code Quality Improvements](#4-code-quality-improvements)
5. [Micro-Optimizations](#5-micro-optimizations)
6. [Summary and Recommendations](#6-summary-and-recommendations)

---

## 1. Philosophy

Since this library has zero users and we're prioritizing elegance, we should:

- **Prefer explicitness over magic** — Clear intent over clever tricks
- **Fail fast with observability** — Log issues rather than silently swallow
- **Single responsibility** — Each component does one thing well
- **Type safety** — Leverage Python's type system fully
- **Memory efficiency** — Use `__slots__` where appropriate

---

## 2. High-Impact Refactorings

### 2.1 Add `cause` Tracking to Errors

**File:** `src/niri_pypc/errors.py`

**Current state:** Uses `raise ... from exc` but doesn't expose `cause` attribute.

**Problem:** Debugging chain of failures is harder without accessible cause.

**Refactoring:**

```python
class NiriError(Exception):
    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        socket_path: str | None = None,
        retryable: bool = False,
        cause: BaseException | None = None,
    ) -> None:
        self.operation = operation
        self.socket_path = socket_path
        self.retryable = retryable
        self.cause = cause
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause
```

All subclasses would inherit the `cause` parameter and pass it to super().

**Impact:** High — improves debuggability significantly.

---

### 2.2 Fix Event Stream Error Handling

**File:** `src/niri_pypc/api/event_stream.py`

**Current state:** Lines 103-105 and 123-124 silently swallow exceptions:

```python
except Exception:
    # Malformed event — skip it
    continue
```

```python
except Exception:
    pass
```

**Problem:** No observability when things go wrong. Silent failures make debugging impossible in production.

**Refactoring:**

```python
import logging

logger = logging.getLogger(__name__)

# In _run_reader:
try:
    decoded = decode_frame(raw)
    event = Event.model_validate(decoded)
except Exception as e:
    logger.warning("Skipping malformed event: %s", e)
    continue
```

And for the reader task:

```python
except asyncio.CancelledError:
    raise  # Re-raise cancellation to exit cleanly
except Exception as e:
    logger.error("Event reader failed: %s", e)
    break
```

**Impact:** High — adds critical observability.

---

### 2.3 Add `skip_to_ready()` to LifecycleManager

**File:** `src/niri_pypc/runtime/lifecycle.py`

**Current state:** `bundle.py:27` accesses private state directly:

```python
self._lifecycle._state = LifecycleState.READY  # skip to ready
```

**Problem:** Bypasses state machine invariants, accesses private API.

**Refactoring:**

```python
class LifecycleManager:
    # ... existing code ...

    async def skip_to_ready(self) -> None:
        """Skip to READY state.
        
        Used by NiriConnectionBundle which has pre-validated both
        client and event connections before constructing the bundle.
        """
        async with self._lock:
            if self._state != LifecycleState.INIT:
                raise LifecycleError(
                    f"Can only skip from INIT, current: {self._state.value}",
                    operation="skip_to_ready",
                    state=self._state.value,
                )
            self._state = LifecycleState.READY
```

Then in `bundle.py`:

```python
await self._lifecycle.skip_to_ready()
```

**Impact:** Medium — cleaner architecture, maintains invariants.

---

### 2.4 Fix codec.getattr() Lint Warning

**File:** `src/niri_pypc/types/codec.py:112`

**Current state:**

```python
payload = getattr(variant, "payload")
```

**Problem:** B009 lint warning — not any safer than direct access.

**Refactoring:**

```python
payload = variant.payload
```

**Impact:** Low — fixes lint warning.

---

### 2.5 Remove or Implement `strict_version_check`

**File:** `src/niri_pypc/config.py:26`

**Current state:** Field defined but never used:

```python
strict_version_check: bool = True
```

**Problem:** Dead code that promises functionality that doesn't exist.

**Refactoring options:**

1. **Remove it** — Simplest, since it's not implemented
2. **Implement it** — Add post-connect version check in client

**Recommendation:** Remove for now. Version checking can be added later when needed.

```python
# Simply remove this line from NiriConfig:
strict_version_check: bool = True
```

**Impact:** Low — removes dead code.

---

## 3. Architectural Improvements

### 3.1 Move Inline Imports to Module Level

**Files:** 
- `src/niri_pypc/api/event_stream.py:66-67`
- `src/niri_pypc/api/client.py:86`

**Current state:** Imports inside functions:

```python
async def connect(...):
    from niri_pypc.types.generated.request import EventStreamRequest
    from niri_pypc.types.generated.request import Request as RequestModel
```

**Problem:** Slight performance cost (import every call), less clean code organization.

**Refactoring:**

```python
# At top of event_stream.py:
from niri_pypc.types.generated.request import EventStreamRequest, Request as RequestModel

# At top of client.py:
from niri_pypc.types.generated.request import Request as RequestModel
from niri_pypc.types.generated.reply import Reply
```

**Impact:** Low — cleaner code, slight performance improvement.

---

### 3.2 Simplify Connection.close()

**File:** `src/niri_pypc/transport/connection.py:166-169`

**Current state:**

```python
try:
    if hasattr(self._writer, "close"):
        self._writer.close()
        if hasattr(self._writer, "wait_closed"):
            await self._writer.wait_closed()
except OSError:
    pass
```

**Problem:** Unnecessary defensive checks — `asyncio.StreamWriter` always has these methods.

**Refactoring:**

```python
async def close(self) -> None:
    if self._closed:
        return
    self._closed = True
    self._writer.close()
    await self._writer.wait_closed()
```

**Impact:** Low — simpler, more readable.

---

### 3.3 Add Type Aliases for Clarity

**File:** `src/niri_pypc/api/event_stream.py`

**Current state:** Complex inline type:

```python
self._queue: asyncio.Queue[BaseModel | _StreamClosed] | None = None
```

**Refactoring:**

```python
from typing import TypeAlias

# At module level:
EventItem: TypeAlias = BaseModel | _StreamClosed

# In class:
self._queue: asyncio.Queue[EventItem] | None = None
```

**Impact:** Low — improved readability.

---

### 3.4 Add Logging for Backpressure Events

**File:** `src/niri_pypc/api/event_stream.py:107-115`

**Current state:**

```python
if config.backpressure_mode == BackpressureMode.DROP_OLDEST:
    try:
        queue.put_nowait(event.variant)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
            queue.put_nowait(event.variant)
        except asyncio.QueueEmpty:
            pass
```

**Problem:** No visibility when events are dropped.

**Refactoring:**

```python
if config.backpressure_mode == BackpressureMode.DROP_OLDEST:
    try:
        queue.put_nowait(event.variant)
    except asyncio.QueueFull:
        # DROP_OLDEST: remove oldest to make room
        dropped = queue.get_nowait()
        logger.warning("Event queue full, dropped oldest event: %s", type(dropped).__name__)
        queue.put_nowait(event.variant)
```

**Impact:** Medium — adds observability for backpressure behavior.

---

## 4. Code Quality Improvements

### 4.1 Add `__slots__` to All Classes

Memory efficiency for classes that may have many instances:

```python
class NiriConfig:
    __slots__ = (
        'socket_path', 'connect_timeout', 'request_timeout',
        'event_read_timeout', 'max_frame_size', 'event_queue_capacity',
        'strict_version_check', 'backpressure_mode'
    )
    # ... rest of class
```

Do this for: `NiriConfig`, `UnixConnection`, `LifecycleManager`, `NiriClient`, `NiriEventStream`, `NiriConnectionBundle`.

**Impact:** Low-Medium — reduces memory per instance.

---

### 4.2 Add Docstrings to Internal Methods

Some internal methods lack complete docstrings. Add for clarity:

```python
async def _close_from_reader(self) -> None:
    """Close the stream from the reader task context.
    
    Called when:
    - Reader encounters TransportError
    - Reader encounters QueueFull in FAIL_FAST mode
    - Reader task is cancelled
    
    Signals stream closure by:
    1. Transitioning to CLOSING
    2. Putting sentinel in queue
    3. Clearing connection reference
    4. Transitioning to CLOSED
    """
```

**Impact:** Low — improves maintainability.

---

### 4.3 Use dataclasses for Simple Models

Consider migrating error classes to dataclass for more concise definition:

```python
@dataclass
class LifecycleError(NiriError):
    state: str | None = None
    
    def __init__(self, message: str, *, state: str | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.state = state
```

**Impact:** Low — cleaner syntax.

---

## 5. Micro-Optimizations

### 5.1 Cache Property Accesses

For properties that are accessed frequently:

```python
# Instead of:
@property
def is_usable(self) -> bool:
    return self._state == LifecycleState.READY

# Consider caching if performance critical:
@property
def is_usable(self) -> bool:
    return self._state.value == "ready"
```

**Impact:** Very low — likely not needed.

---

### 5.2 Use Literal Types for State Values

```python
# In lifecycle.py
_LifecycleStateLiteral: TypeAlias = Literal["init", "connecting", "ready", "closing", "closed"]
```

**Impact:** Very low — type safety improvement.

---

### 5.3 Optimize Queue Operations

The DROP_OLDEST logic could be simplified:

```python
# Current:
except asyncio.QueueFull:
    try:
        queue.get_nowait()
        queue.put_nowait(event.variant)
    except asyncio.QueueEmpty:
        pass

# Cleaner:
except asyncio.QueueFull:
    queue.get_nowait()  # Drops oldest
    queue.put_nowait(event.variant)
```

The QueueEmpty can't happen after QueueFull — it's atomic.

**Impact:** Low — simpler code.

---

## 6. Summary and Recommendations

### Priority Order

| Priority | Refactoring | Impact |
|----------|-------------|--------|
| 1 | Add logging to event stream | High |
| 2 | Add cause to errors | High |
| 3 | Add skip_to_ready() to lifecycle | Medium |
| 4 | Add backpressure logging | Medium |
| 5 | Fix codec getattr | Low |
| 6 | Remove unused strict_version_check | Low |
| 7 | Move imports to module level | Low |
| 8 | Simplify connection.close() | Low |
| 9 | Add type aliases | Low |
| 10 | Add __slots__ | Low |

### Implementation Strategy

1. **Do first:** Items 1-3 (High priority)
2. **Do second:** Items 4-6 (Medium priority)
3. **Do third:** Items 7-10 (Low priority)

### Non-Recommendations

The following were considered but NOT recommended:

- **Removing frozen from NiriConfig** — Immutable config is correct design
- **Adding async generators for events** — Current approach is fine
- **Changing error hierarchy** — Current taxonomy is correct
- **Adding connection pooling** — Out of scope for this library

---

**End of Refactoring Opportunities Document**