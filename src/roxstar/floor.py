"""The speaking floor: only one bot may hold it, so two bots can never talk at once.

Think of it as a talking stick. A bot must acquire the floor before it calls the
LLM or plays audio, and it gives the floor back when it finishes, fails, or is
interrupted. Everyone else waits in line.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from roxstar.domain import Persona


@dataclass(slots=True)
class FloorLease:
    """Proof that one bot currently owns the floor. Use it as ``async with lease:``."""

    persona: Persona
    turn_id: str
    _floor: SpeakingFloor
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    _released: bool = False

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled.is_set()

    def hand_over(self, persona: Persona) -> None:
        """Pass the floor to the next bot in the same plan without releasing it.

        "Kabir answer, Saraah example": no other turn can squeeze in between the two.
        """
        self.persona = persona

    async def __aenter__(self) -> FloorLease:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.release()

    def release(self) -> None:
        """Give the floor back. Safe to call more than once."""
        if not self._released:
            self._released = True
            self._floor._release(self)


class SpeakingFloor:
    """One lock per room. ``acquire`` waits until nobody else is speaking."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._holder: FloorLease | None = None

    @property
    def holder(self) -> Persona | None:
        return self._holder.persona if self._holder else None

    async def acquire(self, *, persona: Persona, turn_id: str) -> FloorLease:
        await self._lock.acquire()
        self._holder = FloorLease(persona=persona, turn_id=turn_id, _floor=self)
        return self._holder

    def interrupt(self) -> bool:
        """Barge-in: tell the current speaker to stop. Returns False if nobody is speaking."""
        if self._holder is None:
            return False
        self._holder.cancelled.set()
        return True

    def _release(self, lease: FloorLease) -> None:
        if self._holder is not lease:
            raise RuntimeError("Only the current floor holder can release the floor")
        self._holder = None
        self._lock.release()
