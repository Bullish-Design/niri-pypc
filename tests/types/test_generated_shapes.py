"""Regression tests for generated protocol type shapes."""

import typing

from niri_pypc.types.generated.action import SpawnAction
from niri_pypc.types.generated.models import (
    LayerSurface,
    Mode,
    Output,
    PickedColor,
    Window,
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


def _get_field_annotation(model_cls, field_name: str):
    """Get the resolved type annotation for a model field."""
    hints = typing.get_type_hints(model_cls)
    return hints[field_name]


class TestResponsePayloadTypes:
    """Verify that Response variant classes carry the correct payload types."""

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
        assert ann == str


class TestModelFieldTypes:
    """Verify that shared model types have correct field types."""

    def test_output_modes_is_list_of_mode(self):
        ann = _get_field_annotation(Output, "modes")
        assert ann == list[Mode]

    def test_spawn_action_command_is_list_of_str(self):
        ann = _get_field_annotation(SpawnAction, "command")
        assert ann == list[str]
