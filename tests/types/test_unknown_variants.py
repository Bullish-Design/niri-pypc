"""Tests for unknown variant sentinel behavior."""

from __future__ import annotations

import pytest

from niri_pypc.types.base import UnknownEvent
from niri_pypc.types.generated.event import Event

pytestmark = pytest.mark.contract


class TestUnknownEvent:
    def test_unknown_event_variant_produces_sentinel(self):
        raw = {"NewFutureEvent": {"some": "data"}}
        event = Event.model_validate(raw)
        assert isinstance(event.root, UnknownEvent)
        assert event.root.variant_name == "NewFutureEvent"
        assert event.root.raw_payload == {"some": "data"}

    def test_unknown_unit_event_produces_sentinel(self):
        raw = "NewFutureUnitEvent"
        event = Event.model_validate(raw)
        assert isinstance(event.root, UnknownEvent)
        assert event.root.variant_name == "NewFutureUnitEvent"

    def test_unknown_after_known_works(self):
        event = Event.model_validate({"WorkspaceActivated": {"id": 1, "focused": True}})
        from niri_pypc.types.generated.event import WorkspaceActivatedEvent

        assert isinstance(event.root, WorkspaceActivatedEvent)
