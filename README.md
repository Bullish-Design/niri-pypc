# niri-pypc

Python protocol client for the [niri](https://github.com/YaLTeR/niri) Wayland compositor.

## Upstream Pin

- **Crate:** `niri-ipc` **25.11**
- **Feature:** `json-schema`

This library is pinned to a specific upstream version. Generated protocol models match `niri-ipc 25.11` exactly. Provenance metadata is tracked in `src/niri_pypc/types/generated/_metadata.py`.

## Installation

```bash
pip install niri-pypc
# or with uv:
uv sync
```

When developing, include dev extras:

```bash
devenv shell -- uv sync --extra dev
```

## Usage

### Basic command request

```python
import asyncio
from niri_pypc import NiriClient, NiriConfig
from niri_pypc.types import VersionRequest


async def main():
    config = NiriConfig()  # or NiriConfig(socket_path=Path("/run/user/1000/niri.sock"))
    async with NiriClient.create(config) as client:
        result = await client.request(VersionRequest())
        print(result.variant.payload)  # e.g., "25.11"


asyncio.run(main())
```

### Event stream

```python
import asyncio
from niri_pypc import NiriEventStream, NiriConfig


async def main():
    config = NiriConfig()
    async with await NiriEventStream.connect(config) as stream:
        async for event in stream:
            print(f"Event: {event}")


asyncio.run(main())
```

### Bundle (command + events)

```python
import asyncio
from niri_pypc import NiriConnectionBundle, NiriConfig
from niri_pypc.types import VersionRequest


async def main():
    config = NiriConfig()
    async with await NiriConnectionBundle.open(config) as bundle:
        version = await bundle.client.request(VersionRequest())
        print(f"Version: {version.variant.payload}")


asyncio.run(main())
```

## Architecture

### Package layout

```
src/niri_pypc/
  __init__.py        # Public API: __version__, NiriClient, NiriEventStream,
                     #   NiriConnectionBundle, NiriConfig, BackpressureMode,
                     #   NiriError + 8 subclasses
  config.py          # NiriConfig (pydantic), BackpressureMode enum
  errors.py          # NiriError taxonomy (9 classes)
  py.typed           # PEP 561 typed marker
  api/
    client.py        # NiriClient — short-lived connection per request()
    event_stream.py  # NiriEventStream — persistent connection + bg reader task
    bundle.py        # NiriConnectionBundle — convenience wrapper for both
  transport/
    connection.py    # UnixConnection — asyncio StreamReader/Writer wrapper
  runtime/
    lifecycle.py     # LifecycleManager state machine
  types/
    base.py          # ProtocolModel, ProtocolVariant, ExternallyTaggedEnum,
                     #   UnknownEvent
    codec.py         # encode_externally_tagged / decode_externally_tagged
    generated/       # Auto-generated types (DO NOT EDIT)
      _metadata.py   # Provenance: upstream crate, version, hashes
      models.py      # Shared struct models (Output, Window, Workspace, etc.)
      request.py     # Request enum (15 variants)
      reply.py       # Reply + Response enums
      event.py       # Event enum (16 variants + UnknownEvent fallback)
      action.py      # Action enum (~85 variants)
```

### Client (NiriClient)

Opens a new `UnixConnection` per `request()` call — no persistent connection, no background tasks. Each request:

1. Resolves the socket path via `NiriConfig.resolve_socket_path()`
2. Connects to the Unix socket
3. Sends the JSON-serialized request with newline delimiter
4. Reads a response frame
5. Validates via `Reply.model_validate_json()`, calls `reply.unwrap()`
6. Closes the connection

Typed overloads provide precise return types for each request variant (e.g. `VersionRequest` -> `VersionResponse`).

### Event stream (NiriEventStream)

Persistent connection with a background reader task and a bounded `asyncio.Queue`:

1. Connects to the Unix socket and performs a bootstrap handshake (sends `EventStream` request, validates `HandledResponse`)
2. Launches `_run_reader()` asyncio task that continuously reads frames and decodes them as `Event`
3. Events are enqueued; consumers pull via `next()` or async iteration
4. Backpressure controlled by `BackpressureMode`:
   - `DROP_OLDEST` (default): drops oldest event when queue is full (with warning)
   - `FAIL_FAST`: raises `ProtocolError` and tears down the stream
5. Unknown event variants are captured as `UnknownEvent` sentinels rather than raising

Lifecycle is managed via `LifecycleManager` (see below).
Use `next()` for explicit terminal/error handling; `async for` treats stream closure as iteration termination.

### Bundle (NiriConnectionBundle)

Convenience wrapper that opens both `NiriClient` and `NiriEventStream`. If the event stream fails to open, the command client is also closed (no leak). Idempotent `close()` propagates the first error.

### Configuration (NiriConfig)

Frozen pydantic model with these fields:

| Field | Default | Description |
|---|---|---|
| `socket_path` | `None` | Explicit socket path, or resolved via `$NIRI_SOCKET` |
| `connect_timeout` | `5.0` | Seconds to wait for socket connection |
| `request_timeout` | `10.0` | Seconds to wait for a request/response exchange |
| `event_read_timeout` | `None` | Seconds for `event_stream.next()` (None = infinite) |
| `max_frame_size` | `4 MiB` | Maximum accepted frame payload size |
| `event_queue_capacity` | `256` | Max in-flight events in the bounded queue |
| `backpressure_mode` | `DROP_OLDEST` | `DROP_OLDEST` or `FAIL_FAST` |

Socket resolution order: `socket_path` field > `$NIRI_SOCKET` env var > `ConfigError`.

### Transport (UnixConnection)

Wraps `asyncio.open_unix_connection` for Unix domain sockets. Frame protocol is **newline-delimited JSON** — `write_frame()` enforces exactly one trailing newline; `read_frame()` reads until `b"\n"`. Error mapping:

- `asyncio.TimeoutError` -> `NiriTimeoutError`
- `OSError` -> `TransportError`
- `IncompleteReadError` -> `TransportError`
- `LimitOverrunError` -> `ProtocolError`

### Lifecycle state machine (LifecycleManager)

Used internally by `NiriEventStream`. Valid transitions:

```
INIT -> CONNECTING
CONNECTING -> READY | CLOSED
READY -> CLOSING
CLOSING -> CLOSED
(any) -> CLOSED   (explicit close)
```

Thread-safe within a single event loop via `asyncio.Lock`.

### Type system

Types are **externally-tagged serde enums** matching niri's JSON wire format. Three variant kinds:

- **unit**: serialized as a bare string — e.g. `"Version"`
- **newtype**: `{"Tag": <payload>}` — wraps a single payload value
- **struct**: `{"Tag": {"field1": val, ...}}` — structured object payload

Base classes:
- **`ProtocolModel`** — frozen pydantic `BaseModel` for all protocol models (extra="forbid", populate_by_name=True)
- **`ProtocolVariant(ProtocolModel)`** — base for enum variants with class vars `__niri_wire_name__` and `__niri_variant_kind__`
- **`ExternallyTaggedEnum[RootT](RootModel[RootT])`** — generic root model with custom `model_validator` and `model_serializer` that delegate to the codec functions
- **`UnknownEvent(ProtocolModel)`** — forward-compatible sentinel capturing `variant_name` + `raw_payload` for unrecognized event variants

Codec functions in `types/codec.py` use the explicit class var metadata (no field-shape heuristics).

### Error taxonomy

All exceptions inherit from `NiriError`, which carries optional context: `operation`, `socket_path`, `retryable`, `cause`.

| Exception | Meaning |
|---|---|
| `TransportError` | Socket or framing I/O failure |
| `NiriTimeoutError` | Connect, request, or event read timeout |
| `DecodeError` | Validation or shape failure during decode |
| `EncodeError` | Failure during outbound encoding |
| `ProtocolError` | Wire-level contract violation |
| `RemoteError` | Error response from the compositor (carries `remote_message`) |
| `LifecycleError` | Invalid state transition or usage (carries `state`) |
| `ConfigError` | Invalid or unresolved configuration |
| `InternalError` | Impossible internal state — indicates a bug |

### Typing support

- `py.typed` marker included for PEP 561 compliant `mypy` / `pyright` / `ty` type-checking
- `__version__` loaded via `importlib.metadata.version("niri-pypc")` at runtime (falls back to `"0.0.0+local"` in source trees)

## Non-Goals

- No state engine or compositor state tracking (see `niri-state` for that)
- No auto-reconnect
- No Windows/macOS support (Unix sockets only)
- No synchronous API (asyncio-only)

## Regeneration

The type generation pipeline has four stages:

```bash
devenv shell -- export-schema    # Export JSON schemas from niri-ipc (Rust)
devenv shell -- normalize-ir     # Normalize schemas into IR JSON
devenv shell -- generate-types   # Generate Pydantic models from IR
devenv shell -- verify-generated  # Verify generated code is up-to-date
```

Or all at once:

```bash
devenv shell -- regen-all
```

Under the hood:
- `tools/schema_exporter/` — Rust crate that depends on `niri-ipc = "=25.11"` and exports JSON Schema files
- `tools/normalize_ir.py` — converts raw JSON Schema exports into normalized IR JSON
- `tools/generate_types.py` — generates `_metadata.py`, `models.py`, `request.py`, `reply.py`, `event.py`, `action.py` from the IR
- `tools/verify_generated.py` — CI check that committed generated files match fresh generation output

## Development

```bash
devenv shell -- uv sync --extra dev
NIRI_PYPC_NESTED_VISIBLE=0 devenv shell -- pytest -m "not nested and not visible_demo and not smoke"  # Safe default tests
devenv shell -- ruff check .     # Lint
devenv shell -- ruff format --check .  # Format check
devenv shell -- ty check .       # Type check
```

Nested/windowed e2e tests (opt-in):

```bash
devenv shell -- pytest -m nested -s
```

Visible watch mode for demos (opens nested compositor window when the host session supports it):

```bash
NIRI_PYPC_ALLOW_VISIBLE_NESTED=1 devenv shell -- pytest -m visible_demo -s --nested-visible
```

Action helper safety:
- `spawn_sh(command)` uses shell interpretation and must not receive untrusted input.
- Prefer `spawn([...])` when arguments originate from untrusted sources.

Useful environment toggles:

```bash
NIRI_PYPC_NESTED_VISIBLE=1              # same as --nested-visible
NIRI_PYPC_ALLOW_VISIBLE_NESTED=1        # explicit unsafe opt-in required for visible mode
NIRI_PYPC_NIRI_BINARY=/path/to/niri     # override niri binary path
NIRI_PYPC_KEEP_NESTED_ARTIFACTS=1       # keep runtime/log dirs on nested startup failure
NIRI_PYPC_NESTED_DEBUG=1                # print nested launch env/socket diagnostics
```

Long-lived visible demo (single nested instance, runs until Ctrl+C):

```bash
NIRI_PYPC_ALLOW_VISIBLE_NESTED=1 devenv shell -- python demo/visual_demo.py
```

Optional demo controls:

```bash
NIRI_PYPC_ALLOW_VISIBLE_NESTED=1 devenv shell -- python demo/visual_demo.py --snapshot-interval 2 --duration 120
```

If the default terminal auto-detection does not open a demo window, set an explicit spawn command:

```bash
NIRI_PYPC_ALLOW_VISIBLE_NESTED=1 devenv shell -- python demo/visual_demo.py --spawn-command "foot"
```

### Visible mode safety rules

- Visible nested mode is fail-closed and requires `NIRI_PYPC_ALLOW_VISIBLE_NESTED=1`.
- Visible nested mode is serial-only (`xdist` workers and `-n > 1` are skipped).
- A cross-process lock prevents concurrent visible nested runs.
- If startup hits compositor/backend failures, a session circuit breaker stops further visible relaunch attempts.

### Incident recovery (visible mode)

1. Validate the active display socket: `test -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY"`.
2. If the socket check fails but compositor processes still exist, treat the session as inconsistent.
3. Close any visible nested test run, clear stale local test artifacts if needed, and retry once.
4. If inconsistencies persist, restart the graphical login session before rerunning visible tests.
