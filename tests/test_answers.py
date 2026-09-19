"""When a bot asks the room a question, the human's answer goes back to that bot."""

from fakes import FakeLLM, make_brain

from roxstar.context import RoomMemory
from roxstar.domain import InputChannel, Persona, UserTurn
from roxstar.routing import Router, RoutingContext, asks_question

VOICE = InputChannel.VOICE
SATHI_ASKS = "Haan Achal, tumhari aawaaz clear aa rahi hai. Batao, aaj kya discuss karna hai?"


def route(text: str, *, asked: bool, humans=frozenset({"Priya"})):
    turn = UserTurn.now(room_name="r", speaker_id="achal", text=text, channel=VOICE)
    context = RoutingContext(
        last_responder=Persona.SATHI,
        bot_spoke_recently=True,
        bot_asked_question=asked,
        other_humans=humans,
    )
    return Router().route(turn, context)


def test_detects_a_reply_that_ends_with_a_question() -> None:
    assert asks_question(SATHI_ASKS)
    assert asks_question('Sach mein?"')
    assert not asks_question("AI ek technology hai.")


def test_an_answer_goes_back_to_the_bot_that_asked() -> None:
    plan = route("कुछ भी यार जो तुम चाहो।", asked=True)  # the exact reply from the live test
    assert plan.responders == (Persona.SATHI,) and plan.reason == "answer"


def test_without_a_question_the_same_words_are_left_alone() -> None:
    assert not route("कुछ भी यार जो तुम चाहो।", asked=False).should_respond


def test_an_answer_aimed_at_another_person_is_left_alone() -> None:
    plan = route("Priya, tum batao na", asked=True)
    assert not plan.should_respond and plan.reason == "asked_another_human"


def test_the_answer_window_closes_after_two_turns() -> None:
    memory = RoomMemory()
    say = lambda text: memory.record_human(  # noqa: E731
        UserTurn.now(room_name="r", speaker_id="achal", text=text, channel=VOICE)
    )
    say("Sathi, meri aawaaz aa rahi hai?")
    memory.record_bot(Persona.SATHI, SATHI_ASKS)
    say("kuch bhi yaar")
    assert memory.routing_context("achal").bot_asked_question
    say("hmm")
    say("accha")
    assert not memory.routing_context("achal").bot_asked_question


async def test_live_bug_answer_to_sathis_question_now_gets_a_reply() -> None:
    brain, bots, _, llm = make_brain(llm=FakeLLM(reply=SATHI_ASKS))
    await brain.handle_turn(speaker="achal", text="Sathi, meri aawaaz aa rahi hai?", channel=VOICE)
    assert bots[Persona.SATHI].chat == [SATHI_ASKS]

    plan = await brain.handle_turn(speaker="achal", text="कुछ भी यार जो तुम चाहो।", channel=VOICE)
    assert plan.responders == (Persona.SATHI,) and plan.reason == "answer"
    assert len(llm.calls) == 2
    assert "कुछ भी यार जो तुम चाहो" in llm.last_prompt()


async def test_an_answer_that_arrives_while_the_bot_is_still_speaking_also_counts() -> None:
    import asyncio

    brain, bots, _, _ = make_brain(llm=FakeLLM(reply=SATHI_ASKS), speak_s=0.2)
    first = asyncio.create_task(
        brain.handle_turn(speaker="achal", text="Sathi, sun rahi ho?", channel=VOICE)
    )
    await asyncio.sleep(0.1)  # Sathi is mid-sentence; the question flag is already set
    plan = await brain.handle_turn(
        speaker="achal", text="haan, kuch bhi", channel=InputChannel.TEXT
    )
    await first
    assert plan.responders == (Persona.SATHI,) and plan.reason == "answer"
