"""Room memory: a sliding window of recent turns plus per-speaker facts.

Context-window strategy (sliding window + rolling summary):
- Keep the last ``max_turns`` turns (default 12) word for word. The prompt size and LLM cost
  stay flat however long the room runs.
- Turns that fall out of the window are not thrown away: they queue up, and every few turns
  the brain asks the LLM (in the background) to fold them into a short running summary.
  The prompt shows "summary of earlier conversation" + the recent turns, so "abhi tak kya
  discuss hua?" covers the whole session.
- Things a person says about themselves ("mera naam Rahul hai", "mujhe cricket pasand hai")
  are copied into that person's fact list, which does NOT drop off with the window. That
  is how "maine apne baare mein kya bataya tha?" still works much later.
- Facts are only shown to the bot when that same person is asking, so Rahul's facts are
  never mixed into Priya's answers.
- An interrupted bot reply is stored as a short marker, not as text nobody heard.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass

from roxstar.domain import Persona, UserTurn
from roxstar.personas import PERSONAS
from roxstar.routing import RoutingContext, asks_question

_SELF_FACT = re.compile(
    r"\b(?:my name is|i like|i love|i live in|i work|i'm from|mera naam|main\b.*\bse hoon|"
    r"mujhe\b.*\bpasand)\b|मेरा नाम|मुझे.*पसंद|मैं.*से हूँ",
    re.IGNORECASE,
)

INTERRUPTED_MARKER = "(was interrupted by the user before finishing this answer)"

# A follow-up only counts if a bot spoke within this many turns before it.
RECENT_BOT_WINDOW = 4
# A human answers a bot's question only if they speak right after it (within 2 turns).
ANSWER_WINDOW = 2


@dataclass(frozen=True, slots=True)
class MemoryTurn:
    speaker: str  # human participant name, or a bot's display name
    text: str
    persona: Persona | None = None  # set only for bot turns


class RoomMemory:
    """One per room. Owned by the room brain; nothing else writes to it."""

    def __init__(self, *, max_turns: int = 12, max_facts_per_speaker: int = 8) -> None:
        if max_turns < 1 or max_facts_per_speaker < 1:
            raise ValueError("Memory limits must be positive")
        self._turns: deque[MemoryTurn] = deque(maxlen=max_turns)
        self._facts: dict[str, deque[str]] = defaultdict(
            lambda: deque(maxlen=max_facts_per_speaker)
        )
        self._last_responder: Persona | None = None
        self._humans: set[str] = set()
        self._turn_count = 0  # every turn ever, not just the ones still in the window
        self._last_bot_at: int | None = None  # turn count when a bot last took the floor
        self._last_bot_asked = False  # the last bot reply ended with a question
        self.summary = ""  # rolling summary of turns that left the window
        self._evicted: list[MemoryTurn] = []  # left the window, not yet in the summary

    @property
    def turns(self) -> tuple[MemoryTurn, ...]:
        return tuple(self._turns)

    @property
    def last_responder(self) -> Persona | None:
        return self._last_responder

    def routing_context(self, speaker: str) -> RoutingContext:
        """Routing facts for ``speaker``'s newest turn (already recorded)."""
        recent = (
            self._last_bot_at is not None
            and self._turn_count - self._last_bot_at <= RECENT_BOT_WINDOW
        )
        awaiting_answer = (
            self._last_bot_asked
            and self._last_bot_at is not None
            and self._turn_count - self._last_bot_at <= ANSWER_WINDOW
        )
        return RoutingContext(
            last_responder=self._last_responder,
            bot_spoke_recently=recent,
            bot_asked_question=awaiting_answer,
            other_humans=frozenset(self._humans - {speaker}),
        )

    @property
    def pending_for_summary(self) -> int:
        return len(self._evicted)

    def take_for_summary(self) -> list[MemoryTurn]:
        batch, self._evicted = self._evicted, []
        return batch

    def return_for_summary(self, batch: list[MemoryTurn]) -> None:
        """Summarizing failed: keep the turns so the next attempt includes them."""
        self._evicted = batch + self._evicted

    def facts_for(self, speaker: str) -> tuple[str, ...]:
        return tuple(self._facts.get(speaker, ()))

    def record_human(self, turn: UserTurn) -> None:
        self._humans.add(turn.speaker_id)
        self._turn_count += 1
        self._append(MemoryTurn(speaker=turn.speaker_id, text=turn.text))
        if _SELF_FACT.search(turn.text) and turn.text not in self._facts[turn.speaker_id]:
            self._facts[turn.speaker_id].append(turn.text)

    def record_bot(self, persona: Persona, text: str, *, interrupted: bool = False) -> None:
        name = PERSONAS[persona].display_name
        self._append(
            MemoryTurn(
                speaker=name, text=INTERRUPTED_MARKER if interrupted else text, persona=persona
            )
        )
        self._turn_count += 1
        # An interrupted reply keeps what was known when it started speaking.
        self.note_responder(persona, asked=None if interrupted else asks_question(text))

    def note_responder(self, persona: Persona, *, asked: bool | None = None) -> None:
        """This bot has the conversation now (called as soon as it starts replying).

        It owns the follow-up: after "Sorry, phir se bolo?", a repeated question goes back
        to it. `asked` records whether its reply ends with a question, so the human's answer
        (even without its name) is routed back to it. None keeps the previous value.
        """
        self._last_responder = persona
        self._last_bot_at = self._turn_count
        if asked is not None:
            self._last_bot_asked = asked

    def _append(self, turn: MemoryTurn) -> None:
        if len(self._turns) == self._turns.maxlen:
            self._evicted.append(self._turns[0])  # about to fall out of the window
        self._turns.append(turn)

    def prompt_context(self, speaker: str) -> str:
        """The room history block that goes into the LLM prompt for ``speaker``'s turn."""
        lines = []
        if self.summary:
            lines += ["Summary of the earlier conversation in this room:", self.summary, ""]
        lines.append("Room conversation so far (oldest first):")
        lines += [f"- {t.speaker}: {t.text}" for t in self._turns] or ["- (nothing yet)"]
        facts = self.facts_for(speaker)
        if facts:
            lines.append(f"What {speaker} has told the room about themselves:")
            lines += [f"- {fact}" for fact in facts]
        return "\n".join(lines)
