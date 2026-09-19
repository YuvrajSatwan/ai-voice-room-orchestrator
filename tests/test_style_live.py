"""Live Hinglish style + relevance evaluation against real Gemini (the assignment scenarios).

Skipped by default. Run with:   ROXSTAR_LIVE_TESTS=1 pytest tests/test_style_live.py -v
It uses the real brain, prompts, memory and routing; only the voices are fakes.
"""

import asyncio
import os

import pytest
from fakes import make_brain
from style import style_problems

from roxstar.config import Settings
from roxstar.domain import InputChannel, Persona
from roxstar.llm import create_reply_fn

pytestmark = pytest.mark.skipif(
    os.getenv("ROXSTAR_LIVE_TESTS") != "1", reason="set ROXSTAR_LIVE_TESTS=1 to call Gemini"
)
VOICE = InputChannel.VOICE
SRK_MOVIES = (
    "dilwale", "chak de", "kuch kuch", "om shanti", "jawan", "pathaan", "swades",
    "devdas", "kal ho na", "my name is khan", "baazigar", "dunki", "veer-zaara",
)  # fmt: skip


@pytest.fixture
def live():
    brain, bots, events, _ = make_brain()
    brain._reply = create_reply_fn(Settings.from_environment(require_livekit=False))
    brain._llm_timeout_s = 30  # judge the words here, not today's API latency

    async def ask(speaker: str, text: str) -> list[str]:
        await asyncio.sleep(4)  # stay under Gemini's per-minute quota (429s otherwise)
        before = {p: len(b.chat) for p, b in bots.items()}
        await brain.handle_turn(speaker=speaker, text=text, channel=VOICE)
        return [msg for p, b in bots.items() for msg in b.chat[before[p] :]]

    return ask, bots


def assert_natural(reply: str) -> None:
    assert not style_problems(reply), f"{style_problems(reply)} in: {reply}"


async def test_s1_natural_hinglish(live) -> None:
    ask, _ = live
    (reply,) = await ask("Rahul", "AI kya hota hai?")
    assert_natural(reply)


async def test_s2_english_question_gets_a_hinglish_answer(live) -> None:
    ask, _ = live
    (reply,) = await ask("Rahul", "Can you explain cloud computing?")
    assert_natural(reply)


async def test_s3_follow_up_resolves_unki(live) -> None:
    ask, _ = live
    await ask("Rahul", "Shah Rukh Khan ke baare mein batao.")
    (reply,) = await ask("Rahul", "Unki koi famous movie batao.")
    assert_natural(reply)
    assert any(movie in reply.lower() for movie in SRK_MOVIES), reply
    assert "atharah" not in reply.lower()  # an early run said DDLJ came out in "atharah sau.."


async def test_s4_second_user_simplifies_the_most_recent_topic_only(live) -> None:
    ask, _ = live
    await ask("Rahul", "Cloud computing kya hai?")
    await ask("Rahul", "AI kya hota hai?")
    (reply,) = await ask("Priya", "Thoda aur simple batao.")
    assert_natural(reply)
    assert "cloud" not in reply.lower(), reply  # simplify AI, not an older topic


async def test_s5_session_memory(live) -> None:
    ask, _ = live
    assert await ask("Rahul", "Mera naam Rahul hai aur mujhe cricket pasand hai.") == []
    (reply,) = await ask("Rahul", "Maine apne baare mein kya bataya tha?")
    assert "cricket" in reply.lower(), reply
    assert_natural(reply)


async def test_s7_two_bots_in_order_with_their_own_gender(live) -> None:
    ask, bots = live
    await ask("Rahul", "AI Dost, tum answer karo. AI Sathi, baad mein ek example dena. Topic: AI")
    (dost,) = bots[Persona.DOST].chat
    (sathi,) = bots[Persona.SATHI].chat
    assert_natural(dost)
    assert_natural(sathi)
    for feminine in ("batati hoon", "gayi hoon", "karti hoon", "deti hoon"):
        assert feminine not in dost.lower(), dost
    for masculine in ("batata hoon", "gaya hoon", "karta hoon", "deta hoon"):
        assert masculine not in sathi.lower(), sathi


async def test_recap_answers_in_natural_hinglish(live) -> None:
    ask, _ = live
    await ask("Rahul", "Cloud computing kya hai?")
    (reply,) = await ask("Rahul", "Abhi tak kya discuss hua?")
    assert "cloud" in reply.lower(), reply
    assert_natural(reply)


async def test_relevance_chatter_gets_no_reply(live) -> None:
    ask, _ = live
    await ask("Rahul", "AI kya hota hai?")
    assert await ask("Rahul", "ohh thank you") == []
    assert await ask("Priya", "Rahul, tum kal cricket khelne aa rahe ho?") == []
