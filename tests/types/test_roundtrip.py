"""Roundtrip tests for generated type models."""

from __future__ import annotations

from niri_pypc.types.generated.event import Event
from niri_pypc.types.generated.reply import Reply
from niri_pypc.types.generated.request import EventStreamRequest, Request, VersionRequest


class TestRequestRoundtrip:
    def test_version_request_unit(self):
        """VersionRequest encodes to 'Version' and decodes back."""
        req = VersionRequest()
        encoded = Request(variant=req).model_dump(mode="json")
        assert encoded == "Version"
        decoded = Request.model_validate("Version")
        assert isinstance(decoded.variant, VersionRequest)

    def test_event_stream_request_unit(self):
        """EventStreamRequest encodes to 'EventStream' and decodes back."""
        req = EventStreamRequest()
        encoded = Request(variant=req).model_dump(mode="json")
        assert encoded == "EventStream"
        decoded = Request.model_validate("EventStream")
        assert isinstance(decoded.variant, EventStreamRequest)


class TestEventRoundtrip:
    def test_workspace_activated_event(self):
        """WorkspaceActivated event roundtrips through model_dump/validate."""
        raw = {"WorkspaceActivated": {"id": 1, "focused": True}}
        event = Event.model_validate(raw)
        encoded = event.model_dump(mode="json")
        assert encoded == raw

    def test_window_closed_event(self):
        """WindowClosed event roundtrips."""
        raw = {"WindowClosed": {"id": 42}}
        event = Event.model_validate(raw)
        encoded = event.model_dump(mode="json")
        assert encoded == raw


class TestReplyRoundtrip:
    def test_ok_version_reply(self):
        """Ok reply wrapping a Version response roundtrips."""
        raw = {"Ok": {"Version": "0.1.0"}}
        reply = Reply.model_validate(raw)
        encoded = reply.model_dump(mode="json")
        assert encoded == raw

    def test_err_reply(self):
        """Err reply roundtrips."""
        raw = {"Err": "something went wrong"}
        reply = Reply.model_validate(raw)
        encoded = reply.model_dump(mode="json")
        assert encoded == raw
