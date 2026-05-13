"""Roundtrip tests for generated type models."""

from __future__ import annotations

import pytest

from niri_pypc.types.generated.event import Event
from niri_pypc.types.generated.reply import Reply
from niri_pypc.types.generated.request import EventStreamRequest, Request, VersionRequest

pytestmark = pytest.mark.contract


class TestRequestRoundtrip:
    def test_version_request_unit(self):
        req = VersionRequest()
        encoded = Request(root=req).model_dump(mode="json")
        assert encoded == "Version"
        decoded = Request.model_validate("Version")
        assert isinstance(decoded.root, VersionRequest)

    def test_event_stream_request_unit(self):
        req = EventStreamRequest()
        encoded = Request(root=req).model_dump(mode="json")
        assert encoded == "EventStream"
        decoded = Request.model_validate("EventStream")
        assert isinstance(decoded.root, EventStreamRequest)


class TestEventRoundtrip:
    def test_workspace_activated_event(self):
        raw = {"WorkspaceActivated": {"id": 1, "focused": True}}
        event = Event.model_validate(raw)
        encoded = event.model_dump(mode="json")
        assert encoded == raw

    def test_window_closed_event(self):
        raw = {"WindowClosed": {"id": 42}}
        event = Event.model_validate(raw)
        encoded = event.model_dump(mode="json")
        assert encoded == raw


class TestReplyRoundtrip:
    def test_ok_version_reply(self):
        raw = {"Ok": {"Version": "0.1.0"}}
        reply = Reply.model_validate(raw)
        encoded = reply.model_dump(mode="json")
        assert encoded == raw

    def test_err_reply(self):
        raw = {"Err": "something went wrong"}
        reply = Reply.model_validate(raw)
        encoded = reply.model_dump(mode="json")
        assert encoded == raw
