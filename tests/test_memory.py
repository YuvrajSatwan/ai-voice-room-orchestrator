from roxstar.context import INTERRUPTED_MARKER, RoomMemory
from roxstar.domain import InputChannel, Persona, UserTurn


def say(memory: RoomMemory, speaker: str, text: str) -> None:
    memory.record_human(
        UserTurn.now(room_name="r", speaker_id=speaker, text=text, channel=InputChannel.VOICE)
    )


def test_window_keeps_only_recent_turns() -> None:
    memory = RoomMemory(max_turns=3)
    for i in range(5):
        say(memory, "Rahul", f"message {i}")
    assert [t.text for t in memory.turns] == ["message 2", "message 3", "message 4"]


def test_self_facts_survive_after_the_turn_leaves_the_window() -> None:
    memory = RoomMemory(max_turns=2)
    say(memory, "Rahul", "Mera naam Rahul hai aur mujhe cricket pasand hai.")
    for i in range(5):
        say(memory, "Rahul", f"filler {i}")
    assert memory.facts_for("Rahul") == ("Mera naam Rahul hai aur mujhe cricket pasand hai.",)
    assert "cricket" in memory.prompt_context("Rahul")


def test_facts_are_only_shown_to_the_person_who_said_them() -> None:
    memory = RoomMemory()
    say(memory, "Rahul", "Mera naam Rahul hai aur mujhe cricket pasand hai.")
    say(memory, "Priya", "मेरा नाम Priya है")
    rahul_facts = memory.prompt_context("Rahul").split("about themselves")[1]
    priya_facts = memory.prompt_context("Priya").split("about themselves")[1]
    assert "cricket" in rahul_facts and "Priya" not in rahul_facts
    assert "Priya" in priya_facts and "cricket" not in priya_facts


def test_ordinary_sentences_are_not_stored_as_facts() -> None:
    memory = RoomMemory()
    say(memory, "Rahul", "AI kya hota hai?")
    assert memory.facts_for("Rahul") == ()


def test_prompt_labels_every_speaker_including_bots() -> None:
    memory = RoomMemory()
    say(memory, "Rahul", "AI kya hota hai?")
    memory.record_bot(Persona.DOST, "AI ek technology hai.")
    context = memory.prompt_context("Rahul")
    assert "- Rahul: AI kya hota hai?" in context
    assert "- Roxstar AI Dost: AI ek technology hai." in context
    assert memory.last_responder is Persona.DOST


def test_interrupted_reply_is_stored_as_a_marker_not_as_unheard_text() -> None:
    memory = RoomMemory()
    memory.record_bot(Persona.SATHI, "A long answer nobody heard", interrupted=True)
    assert memory.turns[-1].text == INTERRUPTED_MARKER
    assert memory.last_responder is Persona.SATHI  # "ruko, simple batao" still goes to Sathi


def test_routing_context_knows_whether_a_bot_spoke_recently() -> None:
    memory = RoomMemory()
    say(memory, "Rahul", "AI kya hai?")
    memory.record_bot(Persona.DOST, "AI ek technology hai.")
    say(memory, "Rahul", "simple batao")
    assert memory.routing_context("Rahul").bot_spoke_recently
    for i in range(5):
        say(memory, "Priya", f"chit chat {i}")
    assert not memory.routing_context("Priya").bot_spoke_recently


def test_routing_context_lists_the_other_humans() -> None:
    memory = RoomMemory()
    say(memory, "Rahul", "hi")
    say(memory, "Priya", "hello")
    assert memory.routing_context("Rahul").other_humans == frozenset({"Priya"})
