"""Test doubles: bots that 'speak' by sleeping, and a scripted LLM. No network needed."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from roxstar.brain import RoomBrain
from roxstar.domain import Persona
from roxstar.personas import PersonaConfiguration


class FakeBot:
    """Records everything it is asked to do into a shared, ordered event log."""

    def __init__(
        self, name: str, events: list[tuple[str, str]], *, speak_s: float = 0.01, tts_fails=False
    ):
        self.name = name
        self.events = events
        self.speak_s = speak_s
        self.tts_fails = tts_fails
        self.chat: list[str] = []

    async def post_text(self, text: str) -> None:
        self.chat.append(text)

    async def speak(
        self, text: str, cancel: asyncio.Event, on_first_audio: Callable[[], None] | None = None
    ) -> bool:
        if self.tts_fails:
            raise RuntimeError("tts down")
        self.events.append((self.name, "start"))
        if on_first_audio:
            on_first_audio()
        try:
            await asyncio.wait_for(cancel.wait(), self.speak_s)
        except TimeoutError:
            self.events.append((self.name, "end"))
            return True
        self.events.append((self.name, "cancelled"))
        return False


class FakeLLM:
    """Returns '<bot> reply N' and keeps every prompt so tests can inspect context."""

    def __init__(
        self, *, fail: bool = False, delay_s: float = 0.0, reply: str | None = None
    ) -> None:
        self.fail = fail
        self.delay_s = delay_s
        self.reply = reply  # a fixed reply text, e.g. one that asks the user a question
        self.calls: list[tuple[Persona, str]] = []

    async def __call__(self, persona: PersonaConfiguration, prompt: str) -> str:
        self.calls.append((persona.identity, prompt))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.fail:
            raise RuntimeError("llm down")
        return self.reply or f"{persona.display_name} reply {len(self.calls)}."

    def last_prompt(self) -> str:
        return self.calls[-1][1]


def make_brain(
    *,
    llm: FakeLLM | None = None,
    speak_s: float = 0.01,
    llm_timeout_s: float = 1.0,
    brain_kw: dict | None = None,
    **bot_kw,
) -> tuple[RoomBrain, dict[Persona, FakeBot], list[tuple[str, str]], FakeLLM]:
    events: list[tuple[str, str]] = []
    bots = {
        Persona.DOST: FakeBot("dost", events, speak_s=speak_s, **bot_kw),
        Persona.SATHI: FakeBot("sathi", events, speak_s=speak_s, **bot_kw),
    }
    llm = llm or FakeLLM()
    brain = RoomBrain(
        bots=bots, reply_fn=llm, room_name="test", llm_timeout_s=llm_timeout_s, **(brain_kw or {})
    )
    return brain, bots, events, llm
