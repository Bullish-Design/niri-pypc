"""Semantic contract tests for the generated protocol types."""

from __future__ import annotations

from pydantic import RootModel

from niri_pypc.types.base import ProtocolVariant
from niri_pypc.types.generated.action import Action, ToggleOverviewAction
from niri_pypc.types.generated.models import ColumnDisplay, Layer, Transform
from niri_pypc.types.generated.reply import ErrReply, Reply
from niri_pypc.types.generated.request import VersionRequest


class TestVariantKindContract:
    def test_toggle_overview_is_struct_variant(self):
        assert issubclass(ToggleOverviewAction, ProtocolVariant)
        assert ToggleOverviewAction.__niri_wire_name__ == "ToggleOverview"
        assert ToggleOverviewAction.__niri_variant_kind__ == "struct"

    def test_version_request_is_unit_variant(self):
        assert VersionRequest.__niri_variant_kind__ == "unit"

    def test_err_reply_is_newtype_variant(self):
        assert ErrReply.__niri_variant_kind__ == "newtype"


class TestRootModelContract:
    def test_action_is_root_model(self):
        assert issubclass(Action, RootModel)

    def test_reply_is_root_model(self):
        assert issubclass(Reply, RootModel)


class TestStrEnumContract:
    def test_transform_is_str_enum(self):
        assert Transform.NORMAL.value == "Normal"
        assert Transform.VALUE_90.value == "90"

    def test_layer_is_str_enum(self):
        assert Layer.TOP.value == "Top"

    def test_column_display_is_str_enum(self):
        assert ColumnDisplay.NORMAL.value == "Normal"


class TestUnknownReplyRemoved:
    def test_unknown_reply_not_importable(self):
        import importlib

        mod = importlib.import_module("niri_pypc.types.generated.reply")
        assert not hasattr(mod, "UnknownReply")


class TestZeroFieldStructWireForm:
    def test_toggle_overview_encodes_as_object(self):
        encoded = Action(root=ToggleOverviewAction()).model_dump(mode="json")
        assert encoded == {"ToggleOverview": {}}


class TestUnitWireForm:
    def test_version_request_encodes_as_string(self):
        from niri_pypc.types.generated.request import Request

        encoded = Request(root=VersionRequest()).model_dump(mode="json")
        assert encoded == "Version"
