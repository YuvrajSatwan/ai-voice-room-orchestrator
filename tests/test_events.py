"""Room events the UI relies on: real orchestration state, never conversation text."""

import asyncio

from fakes import FakeLLM, make_brain

from roxstar.domain import InputChannel

VOICE = InputChannel.VOICE


def brain_with_events(**kw):
    events: list[dict] = []
    brain, bots, spoken, llm = make_brain(brain_kw={"event_sink": events.append}, **kw)
    return brain, events, llm


def names(events: list[dict]) -> list[str]:
    return [e["event"] for e in events]


async def test_a_normal_turn_publishes_routed_thinking_and_turn_done() -> None:
    brain, events, _ = brain_with_events()
    await brain.handle_turn(speaker="Rahul", text="AI kya hota hai?", channel=VOICE)
    assert names(events) == ["routed", "thinking", "turn_done"]
    routed, thinking, done = events
    assert routed == {
        "event": "routed",
        "turn_id": routed["turn_id"],
        "speaker": "Rahul",
        "channel": "voice",
        "bots": ["dost"],
        "reason": "question",
    }
    assert thinking["bot"] == "dost" and thinking["turn_id"] == routed["turn_id"]
    assert done["outcome"] == "spoken" and "first_audio_ms" in done and "llm_ms" in done


async def test_a_silent_turn_still_explains_why() -> None:
    brain, events, _ = brain_with_events()
    await brain.handle_turn(speaker="Rahul", text="ohh thank you", channel=VOICE)
    assert events == [
        {
            "event": "routed",
            "turn_id": events[0]["turn_id"],
            "speaker": "Rahul",
            "channel": "voice",
            "bots": [],
            "reason": "not_for_bots",
        }
    ]


async def test_two_bot_turn_shows_both_bots_in_order() -> None:
    brain, events, _ = brain_with_events()
    await brain.handle_turn(speaker="Rahul", text="Dost answer karo, phir Sathi", channel=VOICE)
    assert [(e["event"], e.get("bot")) for e in events if e["event"] != "routed"] == [
        ("thinking", "dost"),
        ("turn_done", "dost"),
        ("thinking", "sathi"),
        ("turn_done", "sathi"),
    ]


async def test_barge_in_publishes_interrupted() -> None:
    brain, events, _ = brain_with_events(speak_s=5)
    turn = asyncio.create_task(brain.handle_turn(speaker="Rahul", text="AI kya?", channel=VOICE))
    await asyncio.sleep(0.05)
    brain.on_user_started_speaking("Priya")
    await asyncio.wait_for(turn, 1)
    interrupted = next(e for e in events if e["event"] == "interrupted")
    assert interrupted == {"event": "interrupted", "bot": "dost", "by": "Priya"}
    assert events[-1]["outcome"] == "interrupted"


async def test_llm_failure_and_moderation_are_published() -> None:
    brain, events, _ = brain_with_events(llm=FakeLLM(fail=True))
    await brain.handle_turn(speaker="Rahul", text="AI kya hai?", channel=VOICE)
    failed = next(e for e in events if e["event"] == "llm_failed")
    assert failed["bot"] == "dost" and "RuntimeError" in failed["error"]
    assert events[-1]["outcome"] == "fallback_spoken"

    events.clear()
    await brain.handle_turn(speaker="Rahul", text="tu chutiya hai", channel=VOICE)
    assert "moderated" in names(events)


async def test_events_never_carry_conversation_text() -> None:
    brain, events, _ = brain_with_events()
    secret = "mera naam Rahul hai aur mera PIN 4321 hai, batao kya karoon?"
    await brain.handle_turn(speaker="Rahul", text=secret, channel=VOICE)
    assert events and all("4321" not in str(e) and "PIN" not in str(e) for e in events)


async def test_a_broken_event_sink_never_breaks_a_turn() -> None:
    def explode(_event: dict) -> None:
        raise RuntimeError("network down")

    brain, bots, spoken, _ = make_brain(brain_kw={"event_sink": explode})
    await brain.handle_turn(speaker="Rahul", text="AI kya hai?", channel=VOICE)
    assert spoken == [("dost", "start"), ("dost", "end")]
