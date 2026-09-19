"""Small shared types: the two bots, where a turn came from, and a routing decision."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from time import monotonic


class Persona(StrEnum):
    DOST = "dost"
    SATHI = "sathi"


class InputChannel(StrEnum):
    VOICE = "voice"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class UserTurn:
    room_name: str
    speaker_id: str
    text: str
    channel: InputChannel
    received_at_monotonic: float

    @classmethod
    def now(cls, *, room_name: str, speaker_id: str, text: str, channel: InputChannel) -> UserTurn:
        return cls(room_name, speaker_id, text, channel, monotonic())


@dataclass(frozen=True, slots=True)
class ResponseDecision:
    should_respond: bool
    persona: Persona | None
    reason: str

    def __post_init__(self) -> None:
        if self.should_respond != (self.persona is not None):
            raise ValueError("A response decision must name exactly one persona when responding")
