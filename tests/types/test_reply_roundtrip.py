"""Regression test for reply round-trip fidelity."""

import pytest
from pydantic import ValidationError

from niri_pypc.types.generated.reply import Reply

pytestmark = pytest.mark.contract


class TestReplyRoundTrip:
    def test_outputs_response_preserves_payload(self):
        raw = {
            "Ok": {
                "Outputs": {
                    "HDMI-A-1": {
                        "name": "HDMI-A-1",
                        "make": "Dell",
                        "model": "X",
                        "serial": "123",
                        "physical_size": None,
                        "logical": None,
                        "current_mode": None,
                        "is_custom_mode": False,
                        "modes": [],
                        "vrr_supported": False,
                        "vrr_enabled": False,
                    }
                }
            }
        }
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        assert "Ok" in dumped
        inner = dumped["Ok"]
        assert isinstance(inner, dict)
        assert "Outputs" in inner
        outputs = inner["Outputs"]
        assert isinstance(outputs, dict)
        assert "HDMI-A-1" in outputs

    def test_focused_output_null_preserves_null(self):
        raw = {"Ok": {"FocusedOutput": None}}
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        assert dumped == {"Ok": {"FocusedOutput": None}}

    def test_focused_window_with_data_preserves_payload(self):
        raw = {
            "Ok": {
                "FocusedWindow": {
                    "id": 42,
                    "title": "test",
                    "app_id": "test-app",
                    "is_focused": True,
                    "is_floating": False,
                    "is_urgent": False,
                    "layout": {
                        "tile_size": [100.0, 50.0],
                        "window_offset_in_tile": [0.0, 0.0],
                        "window_size": [100, 50],
                    },
                }
            }
        }
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        assert dumped["Ok"]["FocusedWindow"]["id"] == 42

    def test_version_round_trip(self):
        raw = {"Ok": {"Version": "25.11"}}
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        assert dumped == {"Ok": {"Version": "25.11"}}

    def test_err_round_trip(self):
        raw = {"Err": "something went wrong"}
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        assert dumped == {"Err": "something went wrong"}

    def test_windows_response_preserves_list(self):
        raw = {
            "Ok": {
                "Windows": [
                    {
                        "id": 1,
                        "title": "win1",
                        "app_id": "app1",
                        "is_focused": True,
                        "is_floating": False,
                        "is_urgent": False,
                        "layout": {
                            "tile_size": [100.0, 50.0],
                            "window_offset_in_tile": [0.0, 0.0],
                            "window_size": [100, 50],
                        },
                    },
                    {
                        "id": 2,
                        "title": "win2",
                        "app_id": "app2",
                        "is_focused": False,
                        "is_floating": False,
                        "is_urgent": False,
                        "layout": {
                            "tile_size": [120.0, 60.0],
                            "window_offset_in_tile": [1.0, 1.0],
                            "window_size": [120, 60],
                        },
                    },
                ]
            }
        }
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        windows = dumped["Ok"]["Windows"]
        assert len(windows) == 2
        assert windows[0]["id"] == 1

    def test_layers_response_preserves_list(self):
        raw = {
            "Ok": {
                "Layers": [
                    {
                        "namespace": "waybar",
                        "output": "eDP-1",
                        "layer": "Top",
                        "keyboard_interactivity": "None",
                    }
                ]
            }
        }
        reply = Reply.model_validate(raw)
        dumped = reply.model_dump(mode="json")
        layers = dumped["Ok"]["Layers"]
        assert len(layers) == 1
        assert layers[0]["namespace"] == "waybar"

    def test_window_layout_tuple_fields_reject_wrong_lengths(self):
        raw = {
            "Ok": {
                "FocusedWindow": {
                    "id": 42,
                    "title": "test",
                    "app_id": "test-app",
                    "is_focused": True,
                    "is_floating": False,
                    "is_urgent": False,
                    "layout": {
                        "tile_size": [100.0],  # must be length 2
                        "window_offset_in_tile": [0.0, 0.0],
                        "window_size": [100, 50],
                    },
                }
            }
        }
        with pytest.raises(ValidationError):
            Reply.model_validate(raw)
