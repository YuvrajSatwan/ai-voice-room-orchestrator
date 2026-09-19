"""End-to-end brain behaviour for the assignment scenarios, with fake bots and a fake LLM."""

import asyncio

from fakes import FakeLLM, make_brain

from roxstar.brain import FALLBACK_LINES
from roxstar.context import INTERRUPTED_MARKER
from roxstar.domain import InputChannel, Persona

VOICE, TEXT = InputChannel.VOICE, InputChannel.TEXT


async def test_s1_plain_question_is_answered_by_one_bot_in_voice_and_chat() -> None:
    brain, bots, events, _ = make_brain()
    plan = await brain.handle_turn(speaker="Rahul", text="AI kya hota hai?", channel=VOICE)
    assert plan.responders == (Persona.DOST,)
    assert events == [("dost", "start"), ("dost", "end")]
    assert bots[Persona.DOST].chat == ["Kabir reply 1."]
    assert bots[Persona.SATHI].chat == []


async def test_s3_follow_up_prompt_carries_the_earlier_answer() -> None:
    brain, _, _, llm = make_brain()
    await brain.handle_turn(
        speaker="Rahul", text="Shah Rukh Khan ke baare mein batao", channel=VOICE
    )
    await brain.handle_turn(speaker="Rahul", text="Unki koi famous movie batao", channel=VOICE)
    prompt = llm.last_prompt()
    assert "Shah Rukh Khan ke baare mein batao" in prompt
    assert "Kabir: Kabir reply 1." in prompt
    assert 'Rahul said (voice): "Unki koi famous movie batao"' in prompt


async def test_s4_second_user_follow_up_goes_to_the_same_bot_with_shared_context() -> None:
    brain, _, _, llm = make_brain()
    await brain.handle_turn(speaker="Rahul", text="Saraah, AI kya hota hai?", channel=VOICE)
    plan = await brain.handle_turn(speaker="Priya", text="Thoda aur simple batao", channel=VOICE)
    assert plan.responders == (Persona.SATHI,)
    assert "Rahul: Saraah, AI kya hota hai?" in llm.last_prompt()


async def test_s5_speaker_facts_are_recalled_only_for_that_speaker() -> None:
    brain, _, _, llm = make_brain()
    await brain.handle_turn(
        speaker="Rahul", text="Mera naam Rahul hai aur mujhe cricket pasand hai.", channel=TEXT
    )
    await brain.handle_turn(
        speaker="Rahul", text="Maine apne baare mein kya bataya tha?", channel=VOICE
    )
    assert "What Rahul has told the room about themselves" in llm.last_prompt()
    await brain.handle_turn(speaker="Priya", text="Mujhe kya pasand hai?", channel=VOICE)
    assert "What Rahul has told" not in llm.last_prompt()


async def test_voice_and_text_share_one_conversation() -> None:
    brain, _, _, llm = make_brain()
    await brain.handle_turn(speaker="Rahul", text="Cloud computing kya hai?", channel=VOICE)
    await brain.handle_turn(speaker="Priya", text="simple batao", channel=TEXT)
    assert "Rahul: Cloud computing kya hai?" in llm.last_prompt()
    assert "Priya typed in chat" in llm.last_prompt()


async def test_s6_barge_in_stops_the_bot_and_the_next_question_is_answered() -> None:
    brain, _, events, llm = make_brain(speak_s=5)
    turn = asyncio.create_task(
        brain.handle_turn(speaker="Rahul", text="Machine learning samjhao", channel=VOICE)
    )
    await asyncio.sleep(0.05)
    assert brain.on_user_started_speaking("Rahul") is True
    await asyncio.wait_for(turn, 1)
    assert events == [("dost", "start"), ("dost", "cancelled")]
    assert brain.memory.turns[-1].text == INTERRUPTED_MARKER

    for bot in (brain._bots[Persona.DOST], brain._bots[Persona.SATHI]):
        bot.speak_s = 0.01
    await brain.handle_turn(speaker="Rahul", text="Ruko, simple example se samjhao", channel=VOICE)
    assert events[-1] == ("dost", "end")
    assert INTERRUPTED_MARKER in llm.last_prompt()


async def test_barge_in_while_nobody_speaks_does_nothing() -> None:
    brain, _, _, _ = make_brain()
    assert brain.on_user_started_speaking("Rahul") is False


async def test_s7_two_bot_request_runs_in_order_without_overlap() -> None:
    brain, _, events, llm = make_brain()
    await brain.handle_turn(
        speaker="Rahul",
        text="Kabir, tum short answer do. Saraah, tum example dena.",
        channel=VOICE,
    )
    assert events == [("dost", "start"), ("dost", "end"), ("sathi", "start"), ("sathi", "end")]
    sathi_persona, sathi_prompt = llm.calls[1]
    assert sathi_persona is Persona.SATHI
    assert "Kabir reply 1." in sathi_prompt  # Saraah builds on Kabir's answer
    assert "has already answered above" in sathi_prompt


async def test_two_bot_plan_is_not_split_by_another_users_turn() -> None:
    brain, _, events, _ = make_brain(speak_s=0.05)
    both = asyncio.create_task(
        brain.handle_turn(
            speaker="Rahul", text="Kabir answer karo, phir Saraah example", channel=VOICE
        )
    )
    await asyncio.sleep(0.01)
    other = asyncio.create_task(
        brain.handle_turn(speaker="Priya", text="Kabir, cloud kya hai?", channel=TEXT)
    )
    await asyncio.gather(both, other)
    speakers = [name for name, event in events if event == "start"]
    assert speakers == ["dost", "sathi", "dost"]


async def test_simultaneous_turns_from_two_users_never_overlap() -> None:
    brain, _, events, _ = make_brain(speak_s=0.03)
    await asyncio.gather(
        brain.handle_turn(speaker="Rahul", text="Kabir, AI kya hai?", channel=VOICE),
        brain.handle_turn(speaker="Priya", text="Saara, cloud kya hai?", channel=VOICE),
    )
    # Every "start" is immediately followed by the same bot's "end": nobody talks over anyone.
    for i in range(0, len(events), 2):
        assert events[i][1] == "start" and events[i + 1] == (events[i][0], "end")
    assert len(events) == 4


async def test_llm_failure_speaks_a_fallback_and_the_room_keeps_working() -> None:
    llm = FakeLLM(fail=True)
    brain, bots, events, _ = make_brain(llm=llm)
    await brain.handle_turn(speaker="Rahul", text="AI kya hai?", channel=VOICE)
    assert bots[Persona.DOST].chat == [FALLBACK_LINES[Persona.DOST]]
    assert all(t.persona is None for t in brain.memory.turns)  # the apology isn't remembered

    llm.fail = False
    await brain.handle_turn(speaker="Rahul", text="AI kya hai?", channel=VOICE)
    assert bots[Persona.DOST].chat[-1].startswith("Kabir reply")
    assert brain.floor.holder is None


async def test_after_an_apology_the_follow_up_goes_back_to_the_same_bot() -> None:
    llm = FakeLLM(fail=True)
    brain, bots, _, _ = make_brain(llm=llm)
    await brain.handle_turn(speaker="Rahul", text="Saraah, AI kya hota hai?", channel=TEXT)
    llm.fail = False
    plan = await brain.handle_turn(speaker="Rahul", text="Thoda aur simple batao", channel=TEXT)
    assert plan.responders == (Persona.SATHI,)


async def test_follow_up_sent_while_the_bot_is_still_talking_goes_to_that_bot() -> None:
    brain, _, events, _ = make_brain(speak_s=0.1)
    first = asyncio.create_task(
        brain.handle_turn(speaker="Rahul", text="Sarah, AI kya hai?", channel=TEXT)
    )
    await asyncio.sleep(0.05)  # Saraah is mid-sentence
    follow_up = await brain.handle_turn(
        speaker="Rahul", text="thoda aur simple batao", channel=TEXT
    )
    await first
    assert follow_up.responders == (Persona.SATHI,)
    assert [name for name, e in events if e == "start"] == ["sathi", "sathi"]


async def test_llm_timeout_uses_the_fallback() -> None:
    brain, bots, _, _ = make_brain(llm=FakeLLM(delay_s=1), llm_timeout_s=0.05)
    await brain.handle_turn(speaker="Rahul", text="AI kya hai?", channel=VOICE)
    assert bots[Persona.DOST].chat == [FALLBACK_LINES[Persona.DOST]]


async def test_llm_failure_cancels_the_rest_of_a_two_bot_plan() -> None:
    brain, bots, _, _ = make_brain(llm=FakeLLM(fail=True))
    await brain.handle_turn(speaker="Rahul", text="Kabir bolo, phir Saraah", channel=VOICE)
    assert bots[Persona.SATHI].chat == []


async def test_tts_failure_still_delivers_the_reply_as_text() -> None:
    brain, bots, _, _ = make_brain(tts_fails=True)
    await brain.handle_turn(speaker="Rahul", text="AI kya hai?", channel=VOICE)
    assert bots[Persona.DOST].chat == ["Kabir reply 1."]
    assert brain.memory.last_responder is Persona.DOST
    assert brain.floor.holder is None


async def test_submit_turn_logs_crashes_instead_of_raising(caplog) -> None:
    brain, bots, _, _ = make_brain()

    async def broken(*_args, **_kwargs):
        raise ValueError("boom")

    brain._respond = broken  # type: ignore[method-assign]
    await asyncio.wait({brain.submit_turn(speaker="Rahul", text="hi Kabir", channel=TEXT)})
    await asyncio.sleep(0)
    assert "turn_crashed" in caplog.text
    assert brain.floor.holder is None


async def test_empty_turn_is_ignored() -> None:
    brain, _, events, llm = make_brain()
    plan = await brain.handle_turn(speaker="Rahul", text="   ", channel=VOICE)
    assert not plan.should_respond and events == [] and llm.calls == []


async def test_chatter_is_remembered_but_gets_no_reply() -> None:
    brain, _, events, llm = make_brain()
    await brain.handle_turn(speaker="Rahul", text="AI kya hota hai?", channel=VOICE)
    plan = await brain.handle_turn(speaker="Rahul", text="ohh thank you", channel=VOICE)
    assert not plan.should_respond
    assert len(llm.calls) == 1 and len(events) == 2
    assert brain.memory.turns[-1].text == "ohh thank you"  # still part of the context


async def test_humans_talking_to_each_other_are_not_interrupted_by_a_bot() -> None:
    brain, _, events, _ = make_brain()
    await brain.handle_turn(speaker="Priya", text="Hi Rahul, main aa gayi", channel=VOICE)
    plan = await brain.handle_turn(speaker="Rahul", text="Priya, tum kab free ho?", channel=VOICE)
    assert not plan.should_respond and events == []


async def test_s5_full_flow_statement_is_silent_but_recalled_later() -> None:
    brain, _, events, llm = make_brain()
    await brain.handle_turn(
        speaker="Rahul", text="Mera naam Rahul hai aur mujhe cricket pasand hai.", channel=VOICE
    )
    assert events == []  # nothing to answer yet
    await brain.handle_turn(
        speaker="Rahul", text="Maine apne baare mein kya bataya tha?", channel=VOICE
    )
    assert "mujhe cricket pasand hai" in llm.last_prompt()


async def test_demo_switch_fails_the_next_llm_call_once_through_the_real_path() -> None:
    brain, bots, _, llm = make_brain()
    assert brain.simulate_failure("llm")
    await brain.handle_turn(speaker="Rahul", text="AI kya hai?", channel=VOICE)
    assert bots[Persona.DOST].chat == [FALLBACK_LINES[Persona.DOST]]
    assert llm.calls == []  # failed before reaching the model, like a dead provider
    await brain.handle_turn(speaker="Rahul", text="AI kya hai?", channel=VOICE)
    assert bots[Persona.DOST].chat[-1].startswith("Kabir reply")  # one-shot


async def test_demo_switch_for_tts_still_delivers_the_answer_as_text() -> None:
    brain, bots, events, _ = make_brain()
    assert brain.simulate_failure("tts")
    await brain.handle_turn(speaker="Rahul", text="AI kya hai?", channel=VOICE)
    assert bots[Persona.DOST].chat == ["Kabir reply 1."]
    assert events == []  # nothing was spoken
    assert brain.floor.holder is None


async def test_demo_switch_rejects_unknown_stages() -> None:
    brain, _, _, _ = make_brain()
    assert brain.simulate_failure("database") is False


async def test_a_follow_up_prompt_quotes_the_answer_it_follows_up_on() -> None:
    brain, _, _, llm = make_brain()
    await brain.handle_turn(speaker="Rahul", text="Cloud computing kya hai?", channel=VOICE)
    await brain.handle_turn(speaker="Rahul", text="AI kya hota hai?", channel=VOICE)
    await brain.handle_turn(speaker="Priya", text="Thoda aur simple batao", channel=VOICE)
    assert (
        "This is a follow-up to the last answer, by Kabir: "
        '"Kabir reply 2."' in llm.last_prompt()
    )


async def test_a_plain_question_prompt_has_no_follow_up_quote() -> None:
    brain, _, _, llm = make_brain()
    await brain.handle_turn(speaker="Rahul", text="AI kya hota hai?", channel=VOICE)
    assert "This is a follow-up" not in llm.last_prompt()


async def test_reply_text_appears_when_the_voice_starts_not_before() -> None:
    brain, bots, _, _ = make_brain()
    dost = bots[Persona.DOST]
    chat_while_preparing_voice: list[list[str]] = []
    speak = dost.speak

    async def slow_first_sentence(text, cancel, on_first_audio=None):
        await asyncio.sleep(0.05)  # synthesizing the first sentence
        chat_while_preparing_voice.append(list(dost.chat))
        return await speak(text, cancel, on_first_audio)

    dost.speak = slow_first_sentence
    await brain.handle_turn(speaker="Rahul", text="AI kya hota hai?", channel=VOICE)
    assert chat_while_preparing_voice == [[]]
    assert dost.chat == ["Kabir reply 1."]


async def test_reply_text_is_still_posted_if_the_voice_never_starts() -> None:
    brain, bots, _, _ = make_brain()
    dost = bots[Persona.DOST]

    async def cut_off_before_any_audio(text, cancel, on_first_audio=None):
        return False  # interrupted while the first sentence was being synthesized

    dost.speak = cut_off_before_any_audio
    await brain.handle_turn(speaker="Rahul", text="AI kya hota hai?", channel=VOICE)
    assert dost.chat == ["Kabir reply 1."]
