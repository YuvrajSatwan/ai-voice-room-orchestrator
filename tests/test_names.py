"""Kabir and Saraah: how people (and speech-to-text) address them, and how the name is spoken."""

import pytest
from fakes import make_brain

from roxstar.domain import InputChannel, Persona
from roxstar.names import addressed_bots, is_only_a_call
from roxstar.personas import AI_DOST, AI_SATHI, for_speech
from roxstar.routing import Router, RoutingContext
from roxstar.token_server import clean_name

KABIR, SARAAH = Persona.DOST, Persona.SATHI
VOICE, TEXT = InputChannel.VOICE, InputChannel.TEXT


def test_display_names_changed_but_internal_ids_did_not() -> None:
    assert (AI_DOST.display_name, AI_SATHI.display_name) == ("Kabir", "Saraah")
    assert (AI_DOST.livekit_identity, AI_SATHI.livekit_identity) == ("ai-dost", "ai-sathi")
    assert (KABIR.value, SARAAH.value) == ("dost", "sathi")
    assert "You are Kabir." in AI_DOST.instructions()
    assert "You are Saraah." in AI_SATHI.instructions()


@pytest.mark.parametrize(
    "text",
    [
        "Kabir answer karo",
        "Kabir, simple mein bata",
        "Kabir iska example de",
        "Kabir tum kya sochte ho?",
        "KABIR, wahi topic continue karo",
        "kabeer batao",
        "कबीर, cloud क्या है?",
        "AI Dost, tum answer karo",  # the assignment's own wording still works
    ],
)
def test_kabir_is_addressed(text: str) -> None:
    assert addressed_bots(text) == (KABIR,)


@pytest.mark.parametrize(
    "text",
    [
        "Saraah answer karo",
        "Sara answer karo",
        "Saara answer karo",
        "Sarah answer karo",
        "Saraa, example batao",
        "Sarahh please batao",
        "Saara tum answer karo",
        "Sara, iska example batao",
        "Saraah, simple language mein samjhao",
        "Sarah baad mein explain karna",
        "Arre Sara iska answer kya hai?",
        "ok sara, ek aur batao",
        "AI Sara ek example do",
        "सारा, cloud क्या है?",
        "हेलो सारा।",
        "Saraah, kal jo tumne bola tha woh phir se batao",
        "AI Sathi, baad mein ek example dena",  # the assignment's own wording still works
    ],
)
def test_saraah_is_addressed_however_stt_spells_it(text: str) -> None:
    assert addressed_bots(text) == (SARAAH,)


@pytest.mark.parametrize(
    "text",
    [
        "AI kya hota hai?",
        "maine sara kaam kar diya",  # "sara" = "whole" in Hindi
        "Saara din kaam kiya yaar",
        "sara paisa khatam ho gaya",
        "सारा दिन बारिश हुई",
        "mera dost bhi aaya hai",  # old names are ordinary words now
        "saathi log aa gaye",
        "Sarathi movie dekhi?",
        "hum sab saath hain",
    ],
)
def test_ordinary_words_are_not_mistaken_for_a_bot(text: str) -> None:
    assert addressed_bots(text) == ()


@pytest.mark.parametrize(
    ("text", "order"),
    [
        ("Kabir short answer do, Saraah example dena", (KABIR, SARAAH)),
        ("Kabir, tum short answer do. Sara, tum example dena.", (KABIR, SARAAH)),
        ("Saraah pehle bolo, phir Kabir", (SARAAH, KABIR)),
        ("AI Dost, tum answer karo. AI Sathi, baad mein ek example dena.", (KABIR, SARAAH)),
    ],
)
def test_both_named_are_routed_in_the_order_named(text, order) -> None:
    assert addressed_bots(text) == order


def _route(text: str, **context):
    from roxstar.domain import UserTurn

    turn = UserTurn.now(room_name="r", speaker_id="Rahul", text=text, channel=VOICE)
    return Router().route(turn, RoutingContext(**context))


def test_ai_alone_does_not_wake_both_bots() -> None:
    plan = _route("AI kya hota hai?")
    assert plan.responders == (KABIR,) and plan.reason == "question"


def test_a_normal_conversation_with_no_bot_named_stays_silent() -> None:
    for text in ("haan yaar, sara din meeting thi", "ok thik hai", "Priya tum kal aa rahi ho"):
        assert not _route(text, other_humans=frozenset({"Priya"})).should_respond


async def test_two_bot_request_never_overlaps() -> None:
    brain, _, events, _ = make_brain()
    await brain.handle_turn(
        speaker="Rahul", text="Kabir short answer do, Sara example dena", channel=VOICE
    )
    assert events == [("dost", "start"), ("dost", "end"), ("sathi", "start"), ("sathi", "end")]


async def test_each_room_keeps_its_own_context_for_kabir_and_saraah() -> None:
    room_a, _, _, llm_a = make_brain()
    room_b, _, _, llm_b = make_brain()
    await room_a.handle_turn(
        speaker="Rahul", text="Mera naam Rahul hai aur mujhe cricket pasand hai.", channel=TEXT
    )
    await room_a.handle_turn(speaker="Rahul", text="Saraah, mujhe kya pasand hai?", channel=TEXT)
    await room_b.handle_turn(speaker="Rahul", text="Saraah, mujhe kya pasand hai?", channel=TEXT)
    assert "cricket" in llm_a.last_prompt()
    assert "cricket" not in llm_b.last_prompt()


def test_a_bare_name_waits_for_the_rest_of_the_sentence() -> None:
    for fragment in ("Kabir,", "Saraah", "hey Sara,", "हेलो सारा।", "AI Dost"):
        assert is_only_a_call(fragment)
    assert not is_only_a_call("Kabir cloud kya hai?")


def test_the_voice_says_saraah_as_it_is_pronounced_but_the_chat_keeps_the_spelling() -> None:
    spoken = for_speech("Main Saraah hoon, aur yeh Kabir hai.")
    assert spoken == "Main Saara hoon, aur yeh Kabir hai."
    assert for_speech("Saraah") == "Saara"
    assert for_speech("saraahs") == "saraahs"  # only the whole name


@pytest.mark.parametrize("name", ["Kabir", "saraah", "Sara", "Sarah"])
def test_humans_cannot_take_an_ai_name(name: str) -> None:
    with pytest.raises(ValueError):
        clean_name(name)


def test_ordinary_human_names_are_fine() -> None:
    assert clean_name("Sarita") == "Sarita"
    assert clean_name("Rahul") == "Rahul"
