# niri-pypc

Python protocol client for the [niri](https://github.com/YaLTeR/niri) Wayland compositor.

## Upstream Pin

- **Crate:** `niri-ipc` **25.11**
- **Feature:** `json-schema`

This library is pinned to a specific upstream version. Generated protocol models match `niri-ipc 25.11` exactly.

## Installation

```bash
pip install niri-pypc
# or with uv:
uv sync
```

## Usage

### Basic command request

```python
import asyncio
from niri_pypc import NiriClient, NiriConfig
from niri_pypc.types import Request, VersionRequest


async def main():
    config = NiriConfig()  # or NiriConfig(socket_path=Path("/run/user/1000/niri.sock"))
    async with NiriClient.connect(config) as client:
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
from niri_pypc.types import Request, VersionRequest


async def main():
    config = NiriConfig()
    async with await NiriConnectionBundle.open(config) as bundle:
        version = await bundle.client.request(VersionRequest())
        print(f"Version: {version.variant.payload}")
        # Events available via bundle.events


asyncio.run(main())
```

## Architecture

`niri-pypc` is a protocol/runtime substrate. It provides:

- **Generated Pydantic v2 models** for all niri IPC types (`Request`, `Reply`, `Event`, `Action`)
- **Transport layer**: async Unix socket connections with newline-delimited JSON framing
- **Lifecycle management**: state machine enforcing connection lifecycle invariants
- **Error taxonomy**: structured `NiriError` hierarchy with operation/path/retryable context
- **Command client** (`NiriClient`): one-connection-per-request model
- **Event stream** (`NiriEventStream`): persistent connection with bounded queue and backpressure
- **Bundle** (`NiriConnectionBundle`): convenience wrapper with error isolation

## Framing and limits

- Frames are newline-delimited JSON.
- `NiriConfig.max_frame_size` controls the maximum accepted frame payload size.
- Event streaming uses one persistent socket plus a bounded in-memory queue with configurable backpressure behavior.

## Non-Goals

- No state engine or compositor state tracking (see `niri-state` for that)
- No auto-reconnect
- No Windows/macOS support (Unix sockets only)
- No synchronous API (asyncio-only)

## Regeneration

To regenerate protocol models after an upstream pin bump:

```bash
devenv shell -- export-schema    # Export JSON schemas from niri-ipc
devenv shell -- normalize-ir     # Normalize schemas into IR
devenv shell -- generate-types   # Generate Pydantic models from IR
devenv shell -- verify-generated  # Verify generated code is up-to-date
```

Or all at once:

```bash
devenv shell -- regen-all
```

## Development

```bash
devenv shell -- uv sync --extra dev
devenv shell -- pytest           # Run tests
devenv shell -- ruff check .     # Lint
devenv shell -- ruff format --check .  # Format check
devenv shell -- ty check .       # Type check
```
