"""Tests for lifecycle state machine."""

from __future__ import annotations

import pytest

from niri_pypc.api.lifecycle import LifecycleManager, LifecycleState
from niri_pypc.errors import LifecycleError

pytestmark = pytest.mark.contract


class TestLifecycleInitialState:
    async def test_initial_state_is_init(self):
        mgr = LifecycleManager()
        assert mgr.state == LifecycleState.INIT
        assert not mgr.is_usable
        assert not mgr.is_terminal


class TestLifecycleValidTransitions:
    async def test_init_to_connecting(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        assert mgr.state == LifecycleState.CONNECTING

    async def test_connecting_to_ready(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.READY)
        assert mgr.state == LifecycleState.READY
        assert mgr.is_usable

    async def test_connecting_to_closed(self):
        """Connect failure transitions to closed."""
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.CLOSED)
        assert mgr.state == LifecycleState.CLOSED
        assert mgr.is_terminal

    async def test_ready_to_closing(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.READY)
        await mgr.transition_to(LifecycleState.CLOSING)
        assert mgr.state == LifecycleState.CLOSING

    async def test_closing_to_closed(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.READY)
        await mgr.transition_to(LifecycleState.CLOSING)
        await mgr.transition_to(LifecycleState.CLOSED)
        assert mgr.state == LifecycleState.CLOSED
        assert mgr.is_terminal

    async def test_any_state_to_closed(self):
        """Close is allowed from any non-terminal state."""
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CLOSED)
        assert mgr.state == LifecycleState.CLOSED

        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.CLOSED)
        assert mgr.state == LifecycleState.CLOSED

        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.READY)
        await mgr.transition_to(LifecycleState.CLOSED)
        assert mgr.state == LifecycleState.CLOSED

        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.READY)
        await mgr.transition_to(LifecycleState.CLOSING)
        await mgr.transition_to(LifecycleState.CLOSED)
        assert mgr.state == LifecycleState.CLOSED


class TestLifecycleInvalidTransitions:
    async def test_init_to_ready(self):
        mgr = LifecycleManager()
        with pytest.raises(LifecycleError, match="Invalid transition"):
            await mgr.transition_to(LifecycleState.READY)

    async def test_init_to_closing(self):
        mgr = LifecycleManager()
        with pytest.raises(LifecycleError, match="Invalid transition"):
            await mgr.transition_to(LifecycleState.CLOSING)

    async def test_ready_to_init(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.READY)
        with pytest.raises(LifecycleError):
            await mgr.transition_to(LifecycleState.INIT)

    async def test_closed_to_any(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.CLOSED)
        for target in [
            LifecycleState.INIT,
            LifecycleState.CONNECTING,
            LifecycleState.READY,
            LifecycleState.CLOSING,
            LifecycleState.CLOSED,
        ]:
            with pytest.raises(LifecycleError):
                await mgr.transition_to(target)

    async def test_connecting_to_closing(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        with pytest.raises(LifecycleError):
            await mgr.transition_to(LifecycleState.CLOSING)

    async def test_closing_to_ready(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.READY)
        await mgr.transition_to(LifecycleState.CLOSING)
        with pytest.raises(LifecycleError):
            await mgr.transition_to(LifecycleState.READY)


class TestLifecycleRequireState:
    async def test_require_init_allowed(self):
        mgr = LifecycleManager()
        mgr.require_state(LifecycleState.INIT)  # should not raise

    async def test_require_state_raises_on_wrong_state(self):
        mgr = LifecycleManager()
        with pytest.raises(LifecycleError, match="Operation requires state"):
            mgr.require_state(LifecycleState.READY)

    async def test_require_multiple_allowed_states(self):
        mgr = LifecycleManager()
        mgr.require_state(LifecycleState.INIT, LifecycleState.CONNECTING)

    async def test_require_ready_after_transition(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.READY)
        mgr.require_state(LifecycleState.READY)  # should not raise

    async def test_require_usable_after_close(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.CLOSED)
        with pytest.raises(LifecycleError):
            mgr.require_state(LifecycleState.READY)


class TestLifecycleProperties:
    async def test_is_usable_true_when_ready(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.READY)
        assert mgr.is_usable is True

    async def test_is_usable_false_when_not_ready(self):
        mgr = LifecycleManager()
        assert mgr.is_usable is False
        await mgr.transition_to(LifecycleState.CONNECTING)
        assert mgr.is_usable is False
        await mgr.transition_to(LifecycleState.CLOSED)
        assert mgr.is_usable is False

    async def test_is_terminal_true_when_closed(self):
        mgr = LifecycleManager()
        await mgr.transition_to(LifecycleState.CONNECTING)
        await mgr.transition_to(LifecycleState.CLOSED)
        assert mgr.is_terminal is True

    async def test_is_terminal_false_when_not_closed(self):
        mgr = LifecycleManager()
        assert mgr.is_terminal is False
        await mgr.transition_to(LifecycleState.CONNECTING)
        assert mgr.is_terminal is False
        await mgr.transition_to(LifecycleState.READY)
        assert mgr.is_terminal is False
