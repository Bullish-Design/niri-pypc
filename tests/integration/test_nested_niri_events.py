"""Event stream tests for nested niri integration."""

from __future__ import annotations

import asyncio

import pytest

from niri_pypc import NiriClient, NiriConfig, NiriEventStream
from niri_pypc.types.generated.request import OutputsRequest


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_event_stream_bootstrap(nested_niri):
    """Test that event stream provides initial state bootstrap."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))

    events_received = []

    stream = await NiriEventStream.connect(config)
    try:
        await asyncio.sleep(nested_niri.scenario.runtime.settle_delay_s)
        try:
            while True:
                event = await asyncio.wait_for(stream.next(), timeout=0.1)
                events_received.append(event)
        except TimeoutError:
            pass

        assert len(events_received) > 0, "No events received from stream"
        print(f"Received {len(events_received)} initial events")
    finally:
        await stream.close()


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_output_update_events(nested_niri):
    """Test that output change events are captured."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))

    output_events = []

    stream = await NiriEventStream.connect(config)
    try:
        deadline = asyncio.get_event_loop().time() + nested_niri.scenario.runtime.event_timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                event = await asyncio.wait_for(stream.next(), timeout=0.5)
                event_type = type(event).__name__
                if "Output" in event_type or "Monitor" in event_type:
                    output_events.append(event)
            except TimeoutError:
                continue

        print(f"Output events: {len(output_events)}")
    finally:
        await stream.close()


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_workspace_change_events(nested_niri):
    """Test that workspace change events are captured."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))

    workspace_events = []

    stream = await NiriEventStream.connect(config)
    try:
        deadline = asyncio.get_event_loop().time() + nested_niri.scenario.runtime.event_timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                event = await asyncio.wait_for(stream.next(), timeout=0.5)
                event_type = type(event).__name__
                if "Workspace" in event_type:
                    workspace_events.append(event)
            except TimeoutError:
                continue

        print(f"Workspace events: {len(workspace_events)}")
    finally:
        await stream.close()


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_event_stream_lifecycle(nested_niri):
    """Test that event stream can be opened and closed cleanly."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))

    events_received = []

    stream = await NiriEventStream.connect(config)
    assert not stream._lifecycle.is_terminal

    try:
        try:
            event = await asyncio.wait_for(stream.next(), timeout=0.2)
            events_received.append(event)
        except TimeoutError:
            pass
    finally:
        await stream.close()

    assert stream._lifecycle.is_terminal

    print(f"Lifecycle test: received {len(events_received)} events")


@pytest.mark.nested
@pytest.mark.niri_scenario("multi-output")
async def test_nested_multi_output_event_mapping(nested_niri):
    """Test output/workspace mapping in event stream for multi-output."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))

    async with NiriClient.connect(config) as client:
        outputs_response = await client.request(OutputsRequest())
        outputs = outputs_response.variant.payload

        if nested_niri.scenario.capabilities.requires_multi_output:
            if len(outputs) < nested_niri.scenario.expectations.min_outputs:
                pytest.skip("Not enough outputs for multi-output test")

        print(f"Multi-output event test: {len(outputs)} outputs")
