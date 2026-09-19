"""Phase 4 bonus features: the rolling session summary, and basic moderation."""

import asyncio

import pytest
from fakes import make_brain

from roxstar.brain import SUMMARY_BATCH
from roxstar.context import RoomMemory
from roxstar.domain import InputChannel, Persona
from roxstar.moderation import WARNING_LINES, is_abusive, mask

VOICE = InputChannel.VOICE


class FakeSummarizer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.prompts: list[str] = []

    async def __call__(self, system: str, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError("llm down")
        return f"Summary v{len(self.prompts)}: Rahul asked about many topics."


async def chat_until_summarized(brain, turns: int) -> None:
    for i in range(turns):
        await brain.handle_turn(speaker="Rahul", text=f"statement number {i}", channel=VOICE)
    await asyncio.sleep(0.05)  # let the background summary task finish


# Rolling summary -----------------------------------------------------------------------


async def test_turns_leaving_the_window_are_folded_into_a_summary() -> None:
    summarizer = FakeSummarizer()
    brain, *_ = make_brain(brain_kw={"memory": RoomMemory(max_turns=4), "summarize_fn": summarizer})
    await chat_until_summarized(brain, 4 + SUMMARY_BATCH)
    assert brain.memory.summary.startswith("Summary v1")
    assert "statement number 0" in summarizer.prompts[0]  # the evicted turns went in
    assert brain.memory.pending_for_summary == 0


async def test_the_summary_reaches_later_prompts_so_recaps_cover_the_whole_session() -> None:
    brain, _, _, llm = make_brain(
        brain_kw={"memory": RoomMemory(max_turns=4), "summarize_fn": FakeSummarizer()}
    )
    await chat_until_summarized(brain, 4 + SUMMARY_BATCH)
    await brain.handle_turn(speaker="Rahul", text="Abhi tak kya discuss hua?", channel=VOICE)
    assert "Summary of the earlier conversation" in llm.last_prompt()
    assert "Summary v1" in llm.last_prompt()


async def test_a_recap_question_waits_for_a_summary_that_is_being_written() -> None:
    """Found live: the question arrived 0.3 s before the summary update finished."""

    class SlowSummarizer(FakeSummarizer):
        async def __call__(self, system: str, prompt: str) -> str:
            await asyncio.sleep(0.2)
            return await super().__call__(system, prompt)

    brain, _, _, llm = make_brain(
        brain_kw={"memory": RoomMemory(max_turns=4), "summarize_fn": SlowSummarizer()}
    )
    for i in range(4 + SUMMARY_BATCH):  # no pause: the summary is still being written
        await brain.handle_turn(speaker="Rahul", text=f"statement number {i}", channel=VOICE)
    await brain.handle_turn(speaker="Rahul", text="Abhi tak kya discuss hua?", channel=VOICE)
    assert "Summary v1" in llm.last_prompt()


async def test_each_update_builds_on_the_previous_summary() -> None:
    summarizer = FakeSummarizer()
    brain, *_ = make_brain(brain_kw={"memory": RoomMemory(max_turns=4), "summarize_fn": summarizer})
    await chat_until_summarized(brain, 4 + SUMMARY_BATCH)  # first update
    await chat_until_summarized(brain, SUMMARY_BATCH)  # second update, later in the session
    assert len(summarizer.prompts) == 2
    assert "Summary v1" in summarizer.prompts[1]


async def test_a_failed_summary_loses_nothing() -> None:
    summarizer = FakeSummarizer(fail=True)
    brain, *_ = make_brain(brain_kw={"memory": RoomMemory(max_turns=4), "summarize_fn": summarizer})
    await chat_until_summarized(brain, 4 + SUMMARY_BATCH)
    assert brain.memory.summary == ""
    assert brain.memory.pending_for_summary == SUMMARY_BATCH  # kept for the next attempt
    summarizer.fail = False
    await chat_until_summarized(brain, 1)
    assert brain.memory.summary.startswith("Summary")


async def test_summary_questions_are_routed_to_a_bot() -> None:
    brain, _, events, _ = make_brain()
    plan = await brain.handle_turn(speaker="Rahul", text="Abhi tak kya discuss hua?", channel=VOICE)
    assert plan.should_respond
    plan = await brain.handle_turn(speaker="Priya", text="ek recap do", channel=VOICE)
    assert plan.should_respond


# Moderation ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["tu chutiya hai", "Kabir, you are a bitch", "साले हरामी", "bhenchod kya bakwas hai", "BSDK"],
)
def test_abuse_is_detected_in_roman_devanagari_and_english(text: str) -> None:
    assert is_abusive(text)


@pytest.mark.parametrize(
    "text",
    [
        "AI kya hota hai?",
        "yaar ye bakwas hai",  # mild, friends say it
        "pagal hai kya",
        "photo bhejo",
    ],
)
def test_everyday_words_are_not_flagged(text: str) -> None:
    assert not is_abusive(text)


def test_known_trade_off_a_word_list_cannot_read_context() -> None:
    """A slur used as a film title is still flagged. Accepted for a simple, predictable filter."""
    assert is_abusive("Harami movie ka review batao")


def test_mask_hides_only_the_abusive_word() -> None:
    assert mask("Kabir tu chutiya hai kya?") == "Kabir tu *** hai kya?"


async def test_abusive_turn_gets_a_calm_reply_and_never_reaches_the_llm() -> None:
    brain, bots, events, llm = make_brain()
    plan = await brain.handle_turn(speaker="Rahul", text="tu chutiya hai kya", channel=VOICE)
    assert plan.reason == "moderated"
    assert llm.calls == []
    assert bots[Persona.DOST].chat == [WARNING_LINES[Persona.DOST]]
    assert events == [("dost", "start"), ("dost", "end")]
    remembered = [t.text for t in brain.memory.turns]
    assert "tu *** hai kya" in remembered
    assert not any("chutiya" in t for t in remembered)


async def test_abuse_aimed_at_sathi_is_answered_by_sathi() -> None:
    brain, bots, _, _ = make_brain()
    await brain.handle_turn(speaker="Rahul", text="Saraah tu harami hai", channel=VOICE)
    assert bots[Persona.SATHI].chat == [WARNING_LINES[Persona.SATHI]]


async def test_the_room_carries_on_normally_after_a_moderated_turn() -> None:
    brain, bots, _, llm = make_brain()
    await brain.handle_turn(speaker="Rahul", text="bhenchod", channel=VOICE)
    await brain.handle_turn(speaker="Rahul", text="Sorry. AI kya hota hai?", channel=VOICE)
    assert len(llm.calls) == 1
    assert "***" in llm.last_prompt() and "bhenchod" not in llm.last_prompt()
