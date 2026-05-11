"""Lifecycle state machine for niri-pypc connections."""

from __future__ import annotations

import asyncio
import enum

from niri_pypc.errors import LifecycleError


class LifecycleState(enum.Enum):
    INIT = "init"
    CONNECTING = "connecting"
    READY = "ready"
    CLOSING = "closing"
    CLOSED = "closed"


# Valid transition map: current_state -> set of allowed target states
_VALID_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.INIT: {LifecycleState.CONNECTING},
    LifecycleState.CONNECTING: {LifecycleState.READY, LifecycleState.CLOSED},
    LifecycleState.READY: {LifecycleState.CLOSING},
    LifecycleState.CLOSING: {LifecycleState.CLOSED},
    LifecycleState.CLOSED: set(),
}


class LifecycleManager:
    """Manages lifecycle state transitions and enforces invariants.

    Thread-safe: uses asyncio.Lock for state transitions.
    """

    def __init__(self) -> None:
        self._state: LifecycleState = LifecycleState.INIT
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def state(self) -> LifecycleState:
        return self._state

    async def transition_to(self, target: LifecycleState) -> None:
        """Transition to a new state.

        Valid transitions:
            INIT → CONNECTING
            CONNECTING → READY
            CONNECTING → CLOSED (connect failure)
            READY → CLOSING
            CLOSING → CLOSED
            any → CLOSED (via close())

        Raises:
            LifecycleError: On invalid transition.
        """
        async with self._lock:
            allowed = _VALID_TRANSITIONS.get(self._state, set())
            # Allow explicit close from any state (except CLOSED)
            if target == LifecycleState.CLOSED and self._state != LifecycleState.CLOSED:
                self._state = target
                return
            if target not in allowed:
                raise LifecycleError(
                    f"Invalid transition: {self._state.value} → {target.value}",
                    operation="transition_to",
                    state=self._state.value,
                )
            self._state = target

    def require_state(self, *allowed: LifecycleState) -> None:
        """Assert current state is one of the allowed states.

        Raises:
            LifecycleError: If current state is not in allowed set.
        """
        if self._state not in allowed:
            allowed_names = ", ".join(s.value for s in allowed)
            raise LifecycleError(
                f"Operation requires state ({allowed_names}), current: {self._state.value}",
                operation="require_state",
                state=self._state.value,
            )

    @property
    def is_usable(self) -> bool:
        return self._state == LifecycleState.READY

    @property
    def is_terminal(self) -> bool:
        return self._state == LifecycleState.CLOSED
