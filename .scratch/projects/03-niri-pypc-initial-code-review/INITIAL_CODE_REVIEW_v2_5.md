# INITIAL CODE REVIEW — niri-pypc v2.5

**Date:** 2026-05-11  
**Reviewer:** opencode  
**Scope:** Full library implementation per NIRI_PYPC_IMPLEMENTATION_GUIDE.md  
**Version:** niri-ipc 25.11 pinned

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Quality Gate Results](#2-quality-gate-results)
3. [Architecture Assessment](#3-architecture-assessment)
4. [Component-by-Component Review](#4-component-by-component-review)
5. [Generated Code Analysis](#5-generated-code-analysis)
6. [Test Coverage Assessment](#6-test-coverage-assessment)
7. [Issues and Recommendations](#7-issues-and-recommendations)
8. [Verdict](#8-verdict)

---

## 1. Executive Summary

The `niri-pypc` library has been implemented following the concept, spec, and implementation guide documents. The implementation covers:

- **Schema pipeline**: Rust schema exporter → IR normalization → Python type generation
- **Type layer**: Generated Pydantic models with codec helpers for externally-tagged enums
- **Transport layer**: Unix socket connection and newline-delimited JSON framing
- **Runtime layer**: Lifecycle state machine with proper transition guards
- **API layer**: NiriClient (one-connection-per-request), NiriEventStream (persistent connection with backpressure), NiriConnectionBundle (convenience wrapper)

**Overall assessment**: The implementation is functionally complete and mostly well-structured. However, there are several issues that need to be addressed before considering this production-ready.

---

## 2. Quality Gate Results

| Gate | Status | Notes |
|------|--------|-------|
| `pytest -q` | ✅ PASS | 89% coverage, all tests pass |
| `ruff check .` | ⚠️ WARN | 1 B009 lint warning, 1 I001 import sort |
| `ruff format --check .` | ✅ PASS | All files formatted |
| `ty check .` | ❌ FAIL | Type errors in test files |
| `verify-generated` | ❌ FAIL | Generated code has cosmetic diffs |

### 2.1 Lint Issues

**Location:** `src/niri_pypc/types/codec.py:112`

```python
payload = getattr(variant, "payload")
```

**Issue:** B009 - Using `getattr` with a constant attribute value is not safer than normal property access.

**Severity:** Low

**Recommendation:** Replace with direct attribute access:
```python
payload = variant.payload
```

### 2.2 Verify-Generated Failures

The committed generated code differs from what the generator would produce. The differences are cosmetic:

1. **Extra blank lines** between class definitions
2. **Different type annotation formatting** - committed files use multi-line format, regenerated uses single-line

**Severity:** Low (non-functional)

**Recommendation:** Run `normalize-ir && generate-types` to regenerate and commit the properly formatted generated code.

### 2.3 Type Check Failures

Type errors are in test files only (`tests/api/test_bundle.py`), not in source code. The issues involve dictionary typing in mock server fixtures.

**Severity:** Low (test infrastructure only)

---

## 3. Architecture Assessment

### 3.1 Module Structure ✅

The implementation follows the spec's module map:

```
src/niri_pypc/
├── __init__.py          ✅ Public exports
├── errors.py            ✅ Full error taxonomy
├── config.py            ✅ NiriConfig + BackpressureMode
├── types/
│   ├── __init__.py      ✅ Re-exports
│   ├── codec.py         ✅ Externally-tagged helpers
│   └── generated/       ✅ All generated modules
├── transport/
│   ├── connection.py   ✅ UnixConnection
│   └── framing.py       ✅ JSON frame encode/decode
├── runtime/
│   └── lifecycle.py     ✅ LifecycleManager
└── api/
    ├── client.py        ✅ NiriClient
    ├── event_stream.py ✅ NiriEventStream
    └── bundle.py        ✅ NiriConnectionBundle
```

### 3.2 Dependency Direction ✅

The implementation correctly follows the dependency rules from the spec:

- `api → transport, runtime, types, errors, config` ✅
- `transport → runtime, errors` ✅
- `runtime → errors` ✅
- `types → (internal only)` ✅
- `errors → (no deps)` ✅

### 3.3 Public API Surface ✅

The `__init__.py` correctly exports:
- All error classes
- NiriConfig, BackpressureMode
- NiriClient, NiriEventStream, NiriConnectionBundle

Generated types are accessed via `niri_pypc.types` as specified.

---

## 4. Component-by-Component Review

### 4.1 Error Taxonomy (`errors.py`) ✅

**Assessment:** Excellent

The error hierarchy is complete and matches the spec:

| Class | Status |
|-------|--------|
| NiriError | ✅ Base class with operation, socket_path, retryable |
| TransportError | ✅ Socket/framing failures |
| NiriTimeoutError | ✅ Inherits from TimeoutError |
| DecodeError | ✅ With raw_payload |
| ProtocolError | ✅ Wire-level violations |
| RemoteError | ✅ With remote_message |
| LifecycleError | ✅ With state |
| ConfigError | ✅ Invalid/unresolved config |
| InternalError | ✅ Impossible state |

**One note:** The spec mentions `cause` field for wrapped exceptions. The current implementation uses Python's `__cause__` via `raise ... from exc`, which is the idiomatic approach, but doesn't expose a `cause` attribute on the exception itself.

### 4.2 Configuration (`config.py`) ✅

**Assessment:** Good

- `NiriConfig` uses `@dataclass(frozen=True, slots=True)` as specified
- All default values match spec
- Socket resolution precedence is correct: explicit → NIRI_SOCKET → ConfigError

**Minor observation:** The `strict_version_check` config field is defined but never used in the codebase. This appears to be a stub for the version-mismatch policy described in the concept document.

### 4.3 Transport Layer

#### 4.3.1 Framing (`transport/framing.py`) ✅

**Assessment:** Good

- `encode_frame` uses compact JSON separators `(",", ":")` as specified
- `decode_frame` properly catches JSONDecodeError and UnicodeDecodeError
- Raw payload truncation to 1024 bytes is implemented

#### 4.3.2 Connection (`transport/connection.py`) ✅

**Assessment:** Good

- `UnixConnection` wraps asyncio StreamReader/StreamWriter correctly
- All timeouts properly handled with `asyncio.wait_for`
- Error mapping to taxonomy is correct
- `is_closed` property implemented
- Idempotent close implemented

**One concern:** The `close()` method has a minor issue - it checks `hasattr(self._writer, "close")` and `hasattr(self._writer, "wait_closed")` which are always true for StreamWriter. This defensive check is unnecessary but harmless.

### 4.4 Runtime Layer (`runtime/lifecycle.py`) ✅

**Assessment:** Excellent

- All states correctly defined: INIT, CONNECTING, READY, CLOSING, CLOSED
- Valid transition map correctly implemented
- `transition_to` uses asyncio.Lock for thread safety
- `require_state`, `is_usable`, `is_terminal` convenience methods present
- Close-from-any-state is properly allowed

The implementation matches the spec's state transition diagram exactly.

### 4.5 API Layer

#### 4.5.1 Client (`api/client.py`) ✅

**Assessment:** Good

**Correct implementation:**
- One-connection-per-request model as specified
- Proper lifecycle check before request
- Request encoding via model's serializer
- Response decoding and unwrap via `unwrap_reply`
- Proper resource cleanup in finally block
- Async context manager support

**One potential issue:** The `connect()` method validates config by calling `resolve_socket_path()` but doesn't actually open a connection yet (this is correct per spec - "Validates config but does not open a socket yet"). However, if socket path is not set and NIRI_SOCKET is not set, it will raise ConfigError at construction time rather than at request time. This is actually correct behavior.

#### 4.5.2 Event Stream (`api/event_stream.py`) ✅

**Assessment:** Good with concerns

**Correct implementation:**
- Persistent connection model
- Background reader task with proper error handling
- Backpressure modes (DROP_OLDEST, FAIL_FAST) correctly implemented
- Queue capacity respected
- Async iterator support

**Concerns:**

1. **Line 103-105:** Malformed events are silently skipped with `continue`. This could hide real issues:
   ```python
   except Exception:
       # Malformed event — skip it
       continue
   ```
   Should at least log a warning for debugging.

2. **Line 114-115:** The DROP_OLDEST fallback has a subtle issue:
   ```python
   except asyncio.QueueEmpty:
       pass
   ```
   If the queue is empty after a QueueFull (which shouldn't happen), it silently drops the event. This edge case is unlikely but worth noting.

3. **Line 124:** Generic exception catch in reader task:
   ```python
   except Exception:
       pass
   ```
   This silently swallows all exceptions. Should log or handle more gracefully.

4. **Event variant vs payload:** The stream returns `event.variant` (the inner event model) rather than the `Event` wrapper. This is consistent with the API design but worth documenting.

#### 4.5.3 Bundle (`api/bundle.py`) ✅

**Assessment:** Good

- Convenience wrapper correctly implemented
- Independent error isolation between client and events
- Proper cleanup on failure path
- Async context manager support

**One minor issue:** Line 27 directly sets `lifecycle._state = LifecycleState.READY` to skip to READY. This is a private attribute access that bypasses the state machine. While functional, it would be cleaner to add a method to LifecycleManager for this specific bundle use case.

### 4.6 Type Codec (`types/codec.py`) ⚠️

**Assessment:** Good with one lint issue

The codec correctly implements:
- `decode_externally_tagged` with unknown sentinel support
- `encode_externally_tagged` for unit/newtype/struct variants
- `unwrap_reply` for Ok/Err unwrapping

**Lint issue (B009):**
```python
payload = getattr(variant, "payload")
```
Should be `variant.payload` directly.

---

## 5. Generated Code Analysis

### 5.1 Metadata (`types/generated/_metadata.py`) ✅

- Contains all required provenance: upstream crate, version, generator version, IR version, IR hash, schema hashes
- Upstream version correctly shows "25.11"

### 5.2 Type Models

**Request (`request.py`) ✅**
- 14 request variants generated
- Proper variant mapping dicts
- No unknown sentinel (outbound only)

**Reply (`reply.py`) ✅**
- Includes OkReply, ErrReply, UnknownReply
- UnknownReply for inbound unknown variants

**Event (`event.py`) ✅**
- 15 event variants plus UnknownEvent sentinel
- Properly configured for inbound unknown handling

**Action (`action.py`) ✅**
- 78 action variants generated
- All properly mapped

**Models (`models.py`) ✅**
- All struct models: Output, Window, Workspace, etc.
- Internal enum models: Transform, Layer, ColumnDisplay, etc.

### 5.3 Generator Quality

The generated code is syntactically correct and semantically matches the spec. However, the verify-generated failure indicates the generator's formatting output doesn't match the committed files. This is a cosmetic issue that should be resolved.

---

## 6. Test Coverage Assessment

### 6.1 Test Structure

The test suite follows the spec's test directory structure:
- `tests/types/` - roundtrip, golden, unknown variants, edge cases, metadata
- `tests/transport/` - framing, connection
- `tests/api/` - client, event_stream, bundle, lifecycle, config
- `tests/integration/` - command flow, event flow, independence
- `tests/live/` - live smoke tests (gated)

### 6.2 Coverage Report

Overall: **89% coverage**

| Module | Coverage |
|--------|----------|
| api/client.py | 98% |
| api/bundle.py | 80% |
| api/event_stream.py | 80% |
| transport/connection.py | 85% |
| types/codec.py | 91% |
| types/generated/* | 80-100% |
| runtime/lifecycle.py | 100% |
| config.py | 100% |
| errors.py | 100% |

The lower coverage in event_stream and bundle is due to error paths and edge cases being difficult to trigger in tests.

### 6.3 Test Quality

The tests appear comprehensive:
- Roundtrip tests for type encoding/decoding
- Unknown variant sentinel tests
- Mock server for integration tests
- Lifecycle state transition tests

---

## 7. Issues and Recommendations

### 7.1 Critical (Must Fix)

None identified.

### 7.2 High (Should Fix)

| Issue | Location | Description |
|-------|----------|-------------|
| Generator formatting | Generated files | Run `normalize-ir && generate-types` to fix verify-generated failure |
| Unused config field | `config.py:26` | `strict_version_check` is defined but never used |

### 7.3 Medium (Nice to Fix)

| Issue | Location | Description |
|-------|----------|-------------|
| Lint warning | `codec.py:112` | Replace `getattr(variant, "payload")` with direct access |
| Silent exception swallowing | `event_stream.py:103-105, 124` | Log warnings instead of silently dropping malformed events |
| Private state access | `bundle.py:27` | Use proper method instead of `lifecycle._state = ...` |
| Generic exception handling | `event_stream.py:123` | Handle specific exceptions instead of `Exception` |

### 7.4 Low (Optional)

| Issue | Location | Description |
|-------|----------|-------------|
| Defensive hasattr checks | `connection.py:166-169` | Unnecessary but harmless |
| Queue edge case | `event_stream.py:114-115` | Very unlikely edge case in DROP_OLDEST mode |

---

## 8. Verdict

### Summary

The `niri-pypc` library implementation is **functionally complete and well-structured**. It correctly implements the concept, spec, and implementation guide requirements:

- ✅ Full schema → IR → generated type pipeline
- ✅ Correct externally-tagged enum handling
- ✅ Proper Unix socket transport with framing
- ✅ Lifecycle state machine with transition guards
- ✅ Complete error taxonomy
- ✅ One-connection-per-request client
- ✅ Event stream with backpressure modes
- ✅ Convenience bundle wrapper

### Remaining Work

1. **Fix verify-generated**: Run regeneration to fix cosmetic formatting differences
2. **Address lint warning**: Fix B009 in codec.py
3. **Improve event stream error handling**: Add logging for malformed events and silent exception catches
4. **Consider strict_version_check**: Either implement or remove the unused config field

### Recommendation

With the above issues addressed, the library will be ready for production use. The core implementation is solid and follows the specification correctly.

---

**End of Code Review**