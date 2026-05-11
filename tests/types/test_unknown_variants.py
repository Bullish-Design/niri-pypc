"""Tests for unknown variant sentinel behavior."""

from __future__ import annotations

from niri_pypc.types.generated.reply import Reply, UnknownReply
from niri_pypc.types.generated.event import Event, UnknownEvent


class TestUnknownReply:
    def test_unknown_reply_variant_produces_sentinel(self):
        """An unrecognized Reply variant produces UnknownReply sentinel."""
        raw = {"NewFutureReply": {"some": "data"}}
        reply = Reply.model_validate(raw)
        assert isinstance(reply.variant, UnknownReply)
        assert reply.variant.variant_name == "NewFutureReply"
        assert reply.variant.raw_payload == {"some": "data"}

    def test_unknown_unit_reply_produces_sentinel(self):
        """An unrecognized string Reply variant produces UnknownReply."""
        raw = "NewFutureUnitReply"
        reply = Reply.model_validate(raw)
        assert isinstance(reply.variant, UnknownReply)
        assert reply.variant.variant_name == "NewFutureUnitReply"


class TestUnknownEvent:
    def test_unknown_event_variant_produces_sentinel(self):
        """An unrecognized Event variant produces UnknownEvent sentinel."""
        raw = {"NewFutureEvent": {"some": "data"}}
        event = Event.model_validate(raw)
        assert isinstance(event.variant, UnknownEvent)
        assert event.variant.variant_name == "NewFutureEvent"
        assert event.variant.raw_payload == {"some": "data"}

    def test_unknown_unit_event_produces_sentinel(self):
        """An unrecognized string Event variant produces UnknownEvent."""
        raw = "NewFutureUnitEvent"
        event = Event.model_validate(raw)
        assert isinstance(event.variant, UnknownEvent)
        assert event.variant.variant_name == "NewFutureUnitEvent"

    def test_unknown_after_known_works(self):
        """Unknown sentinel does not prevent known events from decoding."""
        event = Event.model_validate({"WorkspaceActivated": {"id": 1, "focused": True}})
        from niri_pypc.types.generated.event import WorkspaceActivatedEvent

        assert isinstance(event.variant, WorkspaceActivatedEvent)
