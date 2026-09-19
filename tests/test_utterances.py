"""Pauses mid-sentence: STT finals from one speaker are joined into one turn."""

import asyncio

import pytest

from roxstar.listener import UtteranceMerger


def merger(**timing) -> tuple[UtteranceMerger, list[str]]:
    delivered: list[str] = []
    timing = {"hold_s": 0.05, "unfinished_hold_s": 0.2, "max_wait_s": 0.5} | timing
    return UtteranceMerger(delivered.append, **timing), delivered


async def test_a_complete_sentence_is_delivered_after_a_short_hold() -> None:
    m, out = merger()
    m.final("AI kya hota hai?")
    assert out == []
    await asyncio.sleep(0.1)
    assert out == ["AI kya hota hai?"]


async def test_bot_name_then_pause_then_question_becomes_one_turn() -> None:
    """The exact split seen live: 'AI साथी।' + pause + 'Cloud Computing क्या होता है?'."""
    m, out = merger()
    m.final("AI साथी।")
    await asyncio.sleep(0.1)  # longer than hold_s: a bare name must not be sent alone
    assert out == []
    m.speech_started()
    await asyncio.sleep(0.05)
    m.final("Cloud Computing क्या होता है?")
    await asyncio.sleep(0.1)
    assert out == ["AI साथी। Cloud Computing क्या होता है?"]


async def test_speaking_again_keeps_the_turn_open_until_the_next_final() -> None:
    m, out = merger()
    m.final("Mujhe batao")
    m.speech_started()
    await asyncio.sleep(0.15)  # past hold_s, but they're still talking
    assert out == []
    m.final("machine learning kya hai")
    await asyncio.sleep(0.1)
    assert out == ["Mujhe batao machine learning kya hai"]


async def test_max_wait_delivers_even_if_the_next_final_never_comes() -> None:
    m, out = merger()
    m.final("Kabir,")
    m.speech_started()  # a cough, then nothing
    await asyncio.sleep(0.6)
    assert out == ["Kabir,"]


async def test_flush_sends_what_was_said_before_the_stream_closed() -> None:
    m, out = merger()
    m.final("thoda aur simple batao")
    m.flush()
    assert out == ["thoda aur simple batao"]
    m.flush()
    assert out == ["thoda aur simple batao"]  # nothing twice


@pytest.mark.parametrize(
    ("text", "unfinished"),
    [
        ("Saraah", True),
        ("Hey Kabir,", True),
        ("हेलो सारा।", True),
        ("AI साथी।", True),
        ("Cloud kya hai aur", True),
        ("Mujhe photo", False),  # ends in "to" inside a word: finished
        ("AI kya hota hai?", False),
    ],
)
async def test_unfinished_fragments_wait_longer(text: str, unfinished: bool) -> None:
    m, out = merger()
    m.final(text)
    await asyncio.sleep(0.1)  # past hold_s, before unfinished_hold_s
    assert (out == []) is unfinished
