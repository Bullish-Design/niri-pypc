"""Basic nested niri integration tests."""

from __future__ import annotations

import pytest

from niri_pypc import NiriClient, NiriConfig
from niri_pypc.types.generated.request import (
    OutputsRequest,
    VersionRequest,
    WindowsRequest,
    WorkspacesRequest,
)


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_version_request_round_trip(nested_niri):
    """Test that Version request succeeds on nested socket."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient.connect(config) as client:
        version = await client.request(VersionRequest())
        assert version is not None
        assert hasattr(version, "variant")
        assert hasattr(version.variant, "payload")
        print(f"Version response: {version.variant.payload}")


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_outputs_snapshot_matches_manifest(nested_niri, scenario_expectations):
    """Test that Outputs request matches scenario manifest expectations."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient.connect(config) as client:
        outputs = await client.request(OutputsRequest())
        assert outputs is not None
        assert len(outputs) >= scenario_expectations.min_outputs
        print(f"Outputs: {list(outputs.keys())}")

        if scenario_expectations.output_names:
            output_names = list(outputs.keys())
            for expected_name in scenario_expectations.output_names:
                assert expected_name in output_names


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_workspaces_snapshot_matches_manifest(nested_niri, scenario_expectations):
    """Test that Workspaces request matches scenario manifest expectations."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient.connect(config) as client:
        workspaces = await client.request(WorkspacesRequest())
        assert workspaces is not None
        assert len(workspaces) >= scenario_expectations.min_workspaces
        print(f"Workspaces: {[(w.name, w.output) for w in workspaces]}")

        if scenario_expectations.workspace_output_map:
            for ws in workspaces:
                if ws.name in scenario_expectations.workspace_output_map:
                    expected_output = scenario_expectations.workspace_output_map[ws.name]
                    assert ws.output == expected_output


@pytest.mark.nested
@pytest.mark.niri_scenario("minimal")
async def test_nested_windows_request_decodes_on_nested_socket(nested_niri, scenario_expectations):
    """Test that Windows request decodes properly on nested socket."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient.connect(config) as client:
        windows = await client.request(WindowsRequest())
        assert windows is not None
        if not scenario_expectations.allow_zero_windows:
            assert len(windows) > 0
        print(f"Windows count: {len(windows)}")


@pytest.mark.nested
@pytest.mark.niri_scenario("multi-output")
async def test_nested_multi_output_scenario(nested_niri):
    """Test multi-output scenario."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient.connect(config) as client:
        outputs = await client.request(OutputsRequest())
        if nested_niri.scenario.capabilities.requires_multi_output:
            if len(outputs) < nested_niri.scenario.expectations.min_outputs:
                pytest.skip(
                    f"Multi-output scenario requires "
                    f"{nested_niri.scenario.expectations.min_outputs} "
                    f"outputs but only {len(outputs)} available"
                )
        assert outputs is not None
        print(f"Multi-output test: {len(outputs)} outputs")


@pytest.mark.nested
@pytest.mark.niri_scenario("dense-workspace")
async def test_nested_dense_workspace_payload(nested_niri, scenario_expectations):
    """Test dense workspace scenario for large payload handling."""
    config = NiriConfig(socket_path=str(nested_niri.socket_path))
    async with NiriClient.connect(config) as client:
        workspaces = await client.request(WorkspacesRequest())
        assert workspaces is not None
        assert len(workspaces) >= scenario_expectations.min_workspaces
        print(f"Dense workspace test: {len(workspaces)} workspaces")
