"""Regression tests for generated protocol type shapes."""

import typing

import pytest

from niri_pypc.types.generated.models import (
    LayerSurface,
    Output,
    PickedColor,
    Window,
    WindowLayout,
    Workspace,
)
from niri_pypc.types.generated.reply import (
    FocusedOutputResponse,
    FocusedWindowResponse,
    LayersResponse,
    OutputsResponse,
    PickedColorResponse,
    PickedWindowResponse,
    VersionResponse,
    WindowsResponse,
    WorkspacesResponse,
)

pytestmark = pytest.mark.contract


def _get_field_annotation(model_cls, field_name: str):
    hints = typing.get_type_hints(model_cls)
    return hints[field_name]


class TestResponsePayloadTypes:
    def test_focused_output_response_has_nullable_output_payload(self):
        ann = _get_field_annotation(FocusedOutputResponse, "payload")
        assert ann == Output | None

    def test_focused_window_response_has_nullable_window_payload(self):
        ann = _get_field_annotation(FocusedWindowResponse, "payload")
        assert ann == Window | None

    def test_picked_color_response_has_nullable_picked_color_payload(self):
        ann = _get_field_annotation(PickedColorResponse, "payload")
        assert ann == PickedColor | None

    def test_picked_window_response_has_nullable_window_payload(self):
        ann = _get_field_annotation(PickedWindowResponse, "payload")
        assert ann == Window | None

    def test_outputs_response_has_dict_payload(self):
        ann = _get_field_annotation(OutputsResponse, "payload")
        assert ann == dict[str, Output]

    def test_layers_response_has_typed_list_payload(self):
        ann = _get_field_annotation(LayersResponse, "payload")
        assert ann == list[LayerSurface]

    def test_windows_response_has_typed_list_payload(self):
        ann = _get_field_annotation(WindowsResponse, "payload")
        assert ann == list[Window]

    def test_workspaces_response_has_typed_list_payload(self):
        ann = _get_field_annotation(WorkspacesResponse, "payload")
        assert ann == list[Workspace]

    def test_version_response_has_str_payload(self):
        ann = _get_field_annotation(VersionResponse, "payload")
        assert ann is str

    def test_output_physical_size_is_fixed_tuple(self):
        ann = _get_field_annotation(Output, "physical_size")
        assert ann == tuple[int, int] | None

    def test_window_layout_fixed_size_fields_are_tuples(self):
        assert _get_field_annotation(WindowLayout, "tile_size") == tuple[float, float]
        assert _get_field_annotation(WindowLayout, "window_offset_in_tile") == tuple[float, float]
        assert _get_field_annotation(WindowLayout, "window_size") == tuple[int, int]
