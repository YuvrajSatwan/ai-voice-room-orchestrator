import asyncio

import pytest

from roxstar.domain import Persona
from roxstar.floor import SpeakingFloor


async def test_second_bot_waits_until_the_first_releases() -> None:
    floor = SpeakingFloor()
    first = await floor.acquire(persona=Persona.DOST, turn_id="t1")
    waiting = asyncio.create_task(floor.acquire(persona=Persona.SATHI, turn_id="t2"))
    await asyncio.sleep(0.01)
    assert not waiting.done() and floor.holder is Persona.DOST

    first.release()
    second = await asyncio.wait_for(waiting, 1)
    assert floor.holder is Persona.SATHI
    second.release()
    assert floor.holder is None


async def test_interrupt_signals_the_current_holder_only() -> None:
    floor = SpeakingFloor()
    assert floor.interrupt() is False  # nobody speaking
    async with await floor.acquire(persona=Persona.DOST, turn_id="t1") as lease:
        assert floor.interrupt() is True
        assert lease.is_cancelled
    fresh = await floor.acquire(persona=Persona.DOST, turn_id="t2")
    assert not fresh.is_cancelled
    fresh.release()


async def test_release_is_idempotent_and_hand_over_keeps_the_floor() -> None:
    floor = SpeakingFloor()
    lease = await floor.acquire(persona=Persona.DOST, turn_id="t1")
    lease.hand_over(Persona.SATHI)
    assert floor.holder is Persona.SATHI
    lease.release()
    lease.release()
    assert floor.holder is None


async def test_only_the_holder_can_release() -> None:
    floor = SpeakingFloor()
    lease = await floor.acquire(persona=Persona.DOST, turn_id="t1")
    lease.release()
    other = await floor.acquire(persona=Persona.SATHI, turn_id="t2")
    with pytest.raises(RuntimeError):
        floor._release(lease)
    other.release()
