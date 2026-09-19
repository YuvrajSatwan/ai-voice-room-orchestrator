"""The small pure helpers around LiveKit: chat parsing, sentence splitting, cancellation."""

import asyncio
import json
from types import SimpleNamespace

from livekit import rtc

from roxstar.voices import _unless_cancelled, split_sentences
from roxstar.worker import parse_chat

HUMAN = rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD
AGENT = rtc.ParticipantKind.PARTICIPANT_KIND_AGENT


def packet(payload: object, *, kind: int = HUMAN) -> SimpleNamespace:
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return SimpleNamespace(data=data, participant=SimpleNamespace(identity="Rahul", kind=kind))


def test_parse_chat_accepts_human_chat_messages() -> None:
    assert parse_chat(packet({"type": "roxstar.chat", "text": " AI kya hai? "})) == "AI kya hai?"


def test_parse_chat_ignores_bot_messages_so_replies_never_loop() -> None:
    assert parse_chat(packet({"type": "roxstar.chat", "text": "hi"}, kind=AGENT)) is None


def test_parse_chat_ignores_other_and_malformed_packets() -> None:
    assert parse_chat(packet({"type": "something-else", "text": "hi"})) is None
    assert parse_chat(packet(b"\xff\xfe not json")) is None
    assert parse_chat(packet({"type": "roxstar.chat", "text": "   "})) is None


def test_split_sentences_handles_english_and_devanagari_punctuation() -> None:
    text = "AI ek technology hai. Ye machine ko smart banati hai! Samjhe? हाँ। ठीक है"
    assert split_sentences(text) == [
        "AI ek technology hai.",
        "Ye machine ko smart banati hai!",
        "Samjhe?",
        "हाँ।",
        "ठीक है",
    ]


async def test_unless_cancelled_returns_the_result_when_not_cancelled() -> None:
    work = asyncio.ensure_future(asyncio.sleep(0.01, result="audio"))
    assert await _unless_cancelled(work, asyncio.Event()) == (True, "audio")


async def test_unless_cancelled_stops_work_as_soon_as_cancel_fires() -> None:
    cancel = asyncio.Event()
    work = asyncio.ensure_future(asyncio.sleep(5))
    asyncio.get_running_loop().call_later(0.01, cancel.set)
    assert await asyncio.wait_for(_unless_cancelled(work, cancel), 1) == (False, None)
    await asyncio.sleep(0)
    assert work.cancelled()
