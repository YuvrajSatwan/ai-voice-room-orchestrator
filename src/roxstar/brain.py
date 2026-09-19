"""The room brain: every human turn, spoken or typed, goes through ``handle_turn``.

    turn in -> remember it -> route -> take the floor -> for each chosen bot:
        LLM reply -> post to chat -> speak -> remember the reply

It never touches LiveKit or a vendor SDK directly; it talks to bots through the small
``BotOutput`` interface and to the model through ``ReplyFn``. That keeps it fully
testable with fakes.

Room events: every decision it already logs (routed, thinking, interrupted, turn_done with
latency, llm_failed, ...) is also handed to ``event_sink``. The worker publishes these into
the room, so the UI can show real orchestration state. Events never carry conversation text.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable, Mapping, Sequence
from time import monotonic
from typing import Any, Protocol

from roxstar.context import INTERRUPTED_MARKER, MemoryTurn, RoomMemory
from roxstar.domain import InputChannel, Persona, UserTurn
from roxstar.floor import FloorLease, SpeakingFloor
from roxstar.llm import ReplyFn, TextFn
from roxstar.log import get_logger
from roxstar.moderation import WARNING_LINES, is_abusive, mask
from roxstar.personas import PERSONAS
from roxstar.routing import ResponsePlan, Router, asks_question
from roxstar.telemetry import TurnTimer

_log = get_logger("brain")

# Spoken when the LLM is down, so the room hears a human-sounding apology, not silence.
FALLBACK_LINES = {
    Persona.DOST: "Sorry yaar, mera connection thoda atak gaya. Ek baar phir se bolo?",
    Persona.SATHI: "Oops, network mein thodi dikkat aa gayi. Ek baar phir se poochoge?",
}


# Fold turns that left the memory window into the running summary once this many pile up.
SUMMARY_BATCH = 6
SUMMARIZER_INSTRUCTIONS = """\
You maintain a short running summary of a live voice-room conversation between humans and
two AI assistants (Kabir, Saraah). Merge the new turns into the existing
summary. Write at most 120 words of plain English: who asked about which topics and the key
points the assistants gave. Do NOT include personal details people shared about themselves
(hobbies, locations, jobs, etc.); those are stored separately and are private. Output only
the updated summary."""

# Stages a demo can make fail on purpose (see ``simulate_failure``).
FAILABLE_STAGES = ("llm", "tts")


class SimulatedFailure(RuntimeError):
    """Raised on purpose by ``simulate_failure`` to demo the real error handling."""


class BotOutput(Protocol):
    """What the brain needs from a bot participant in the room."""

    async def speak(
        self, text: str, cancel: asyncio.Event, on_first_audio: Callable[[], None] | None = None
    ) -> bool:
        """Play ``text`` as audio. Return True if it finished, False if cancelled."""

    async def post_text(self, text: str) -> None:
        """Publish ``text`` to the room chat as this bot."""


class RoomBrain:
    def __init__(
        self,
        *,
        bots: Mapping[Persona, BotOutput],
        reply_fn: ReplyFn,
        summarize_fn: TextFn | None = None,
        room_name: str = "room",
        memory: RoomMemory | None = None,
        router: Router | None = None,
        floor: SpeakingFloor | None = None,
        llm_timeout_s: float = 12.0,  # covers the main model plus one fallback
        log_transcripts: bool = False,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.memory = memory or RoomMemory()
        self.floor = floor or SpeakingFloor()
        self._router = router or Router()
        self._bots = bots
        self._reply = reply_fn
        self._room_name = room_name
        self._llm_timeout_s = llm_timeout_s
        self._log_transcripts = log_transcripts
        self._tasks: set[asyncio.Task[ResponsePlan]] = set()
        self._fail_next: set[str] = set()
        self._summarize = summarize_fn
        self._summary_task: asyncio.Task[None] | None = None
        self._event_sink = event_sink

    def on_user_started_speaking(self, speaker: str) -> bool:
        """Barge-in: a human started talking, so whichever bot is speaking stops."""
        bot = self.floor.holder
        if not self.floor.interrupt():
            return False
        _log.info("barge_in", extra={"speaker": speaker, "bot": bot})
        self._emit("interrupted", bot=bot.value if bot else None, by=speaker)
        return True

    def simulate_failure(self, stage: str) -> bool:
        """Demo only: make the next ``stage`` call fail, through the real error-handling path.

        Used to show "one expected provider failure" on camera without pulling the network.
        """
        if stage not in FAILABLE_STAGES:
            return False
        self._fail_next.add(stage)
        _log.warning("failure_armed", extra={"stage": stage})
        self._emit("failure_armed", stage=stage)
        return True

    def _maybe_fail(self, stage: str) -> None:
        if stage in self._fail_next:
            self._fail_next.discard(stage)
            raise SimulatedFailure(f"simulated {stage} failure (demo)")

    def submit_turn(
        self, *, speaker: str, text: str, channel: InputChannel
    ) -> asyncio.Task[ResponsePlan]:
        """Fire-and-forget entry point for LiveKit callbacks; a crash is logged, never raised."""
        task = asyncio.create_task(self.handle_turn(speaker=speaker, text=text, channel=channel))
        self._tasks.add(task)
        task.add_done_callback(self._on_turn_done)
        return task

    def _on_turn_done(self, task: asyncio.Task[ResponsePlan]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            _log.error("turn_crashed", extra={"error": type(task.exception()).__name__})

    async def handle_turn(self, *, speaker: str, text: str, channel: InputChannel) -> ResponsePlan:
        try:
            return await self._handle_turn(speaker, text.strip(), channel)
        finally:
            self._maybe_summarize()

    async def _handle_turn(self, speaker: str, text: str, channel: InputChannel) -> ResponsePlan:
        started_at = monotonic()
        if not text:
            return ResponsePlan.silent("empty")

        turn_id = uuid.uuid4().hex[:8]
        abusive = is_abusive(text)
        user_turn = UserTurn.now(
            room_name=self._room_name,
            speaker_id=speaker,
            text=mask(text) if abusive else text,  # the slur never enters memory or a prompt
            channel=channel,
        )
        self.memory.record_human(user_turn)
        if abusive:
            return await self._answer_abuse(user_turn, turn_id, started_at)
        plan = self._router.route(user_turn, self.memory.routing_context(speaker))
        _log.info(
            "turn_routed",
            extra={
                "turn_id": turn_id,
                "speaker": speaker,
                "channel": channel.value,
                "bots": [p.value for p in plan.responders],
                "reason": plan.reason,
                **self._maybe_text(text),
            },
        )
        self._emit(
            "routed",
            turn_id=turn_id,
            speaker=speaker,
            channel=channel.value,
            bots=[p.value for p in plan.responders],
            reason=plan.reason,
        )
        if not plan.should_respond:
            return plan

        responders = plan.responders
        lease = await self.floor.acquire(persona=responders[0], turn_id=turn_id)
        async with lease:
            done: list[Persona] = []
            for persona in responders:
                lease.hand_over(persona)
                finished = await self._respond(
                    lease,
                    persona,
                    user_turn,
                    done,
                    started_at,
                    follow_up=plan.reason == "follow_up",
                )
                if not finished:
                    break  # interrupted or failed: the rest of the plan is dropped
                done.append(persona)
        return plan

    async def _answer_abuse(self, turn: UserTurn, turn_id: str, started_at: float) -> ResponsePlan:
        """Moderation: a calm fixed reply from one bot. The LLM is never called."""
        context = self.memory.routing_context(turn.speaker_id)
        named = self._router.named_personas(turn.text)
        recent = context.last_responder if context.bot_spoke_recently else None
        persona = named[0] if named else (recent or Persona.DOST)
        _log.warning(
            "moderation_flagged",
            extra={"turn_id": turn_id, "speaker": turn.speaker_id, "bot": persona.value},
        )
        self._emit("moderated", turn_id=turn_id, speaker=turn.speaker_id, bot=persona.value)
        async with await self.floor.acquire(persona=persona, turn_id=turn_id) as lease:
            await self._respond(
                lease, persona, turn, (), started_at, fixed_reply=WARNING_LINES[persona]
            )
        return ResponsePlan.silent("moderated")

    def _maybe_summarize(self) -> None:
        """Start one background summary update once enough turns have left the window."""
        if self._summarize is None or self.memory.pending_for_summary < SUMMARY_BATCH:
            return
        if self._summary_task is not None and not self._summary_task.done():
            return
        self._summary_task = asyncio.create_task(self._update_summary())

    async def _summary_settled(self, max_wait_s: float = 3.0) -> None:
        """If the summary is being updated right now, wait briefly so the prompt includes it.

        Found live: "abhi tak kya discuss hua?" arrived 0.3 s before a summary update
        finished, and the recap missed the older topics.
        """
        task = self._summary_task
        if task is not None and not task.done():
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.shield(task), max_wait_s)

    async def _update_summary(self) -> None:
        batch = self.memory.take_for_summary()
        lines = "\n".join(f"- {t.speaker}: {t.text}" for t in batch)
        prompt = (
            f"Existing summary:\n{self.memory.summary or '(none yet)'}\n\n"
            f"New turns to merge (oldest first):\n{lines}"
        )
        try:
            self.memory.summary = await asyncio.wait_for(
                self._summarize(SUMMARIZER_INSTRUCTIONS, prompt), 30
            )
            _log.info("summary_updated", extra={"turns_merged": len(batch)})
            self._emit("summary_updated", turns_merged=len(batch))
        except Exception as exc:
            self.memory.return_for_summary(batch)  # nothing lost; retried after the next turn
            _log.warning("summary_failed", extra={"error": _describe(exc)})

    async def _respond(
        self,
        lease: FloorLease,
        persona: Persona,
        turn: UserTurn,
        already_answered: Sequence[Persona],
        started_at: float,
        *,
        fixed_reply: str | None = None,
        follow_up: bool = False,
    ) -> bool:
        """One bot's reply. Returns True only if it was fully delivered."""
        cfg = PERSONAS[persona]
        timer = TurnTimer(
            turn_id=lease.turn_id,
            speaker=turn.speaker_id,
            channel=turn.channel.value,
            bot=persona.value,
            started_at=started_at,
        )
        timer.mark("floor")

        llm_ok = True
        try:
            if fixed_reply is not None:
                reply = fixed_reply
            else:
                await self._summary_settled()
                self._emit("thinking", turn_id=lease.turn_id, bot=persona.value)
                prompt = self._build_prompt(turn, already_answered, follow_up=follow_up)
                self._maybe_fail("llm")
                reply = await asyncio.wait_for(self._reply(cfg, prompt), self._llm_timeout_s)
                timer.mark("llm")
        except Exception as exc:  # timeout, provider error, empty reply
            llm_ok = False
            reply = FALLBACK_LINES[persona]
            _log.warning(
                "llm_failed",
                extra={"turn_id": lease.turn_id, "bot": persona.value, "error": _describe(exc)},
            )
            self._emit("llm_failed", turn_id=lease.turn_id, bot=persona.value, error=_describe(exc))

        if lease.is_cancelled:  # user started talking while the model was thinking
            self._finish(timer, "interrupted_before_speaking")
            return False

        _log.info(
            "bot_reply",
            extra={
                "turn_id": lease.turn_id,
                "bot": persona.value,
                "chars": len(reply),
                **self._maybe_text(reply),
            },
        )
        # The bot owns the topic from the moment it starts answering, so a follow-up that
        # arrives while it is still talking ("thoda aur simple batao") comes back to it.
        self.memory.note_responder(persona, asked=asks_question(reply))
        bot = self._bots[persona]

        # The text appears in the chat when the voice starts, not before: synthesizing the
        # first sentence takes ~2 s, and text that far ahead of the voice looks out of sync.
        # If the voice never starts (TTS failed, or the user interrupted first), the text is
        # still posted afterwards, so the room always gets the answer.
        posting: asyncio.Task[None] | None = None

        async def post() -> None:
            try:
                await bot.post_text(reply)
                timer.mark("chat_posted")
            except Exception as exc:
                _log.warning(
                    "chat_publish_failed", extra={"bot": persona.value, "error": type(exc).__name__}
                )

        def on_first_audio() -> None:
            nonlocal posting
            timer.mark("first_audio")
            posting = asyncio.create_task(post())

        async def ensure_posted() -> None:
            await (posting if posting is not None else post())

        try:
            self._maybe_fail("tts")
            finished = await bot.speak(reply, lease.cancelled, on_first_audio)
        except Exception as exc:
            # Voice failed, but the reply still reaches the chat, so the room has it.
            await ensure_posted()
            _log.warning(
                "tts_failed",
                extra={"turn_id": lease.turn_id, "bot": persona.value, "error": type(exc).__name__},
            )
            self._emit(
                "tts_failed", turn_id=lease.turn_id, bot=persona.value, error=type(exc).__name__
            )
            if llm_ok:
                self.memory.record_bot(persona, reply)
            self._finish(timer, "text_only")
            return llm_ok

        await ensure_posted()
        if not finished:
            self.memory.record_bot(persona, reply, interrupted=True)
            self._finish(timer, "interrupted")
            return False

        if llm_ok:
            self.memory.record_bot(persona, reply)
        self._finish(timer, "spoken" if llm_ok else "fallback_spoken")
        return llm_ok

    def _build_prompt(
        self, turn: UserTurn, already_answered: Sequence[Persona], *, follow_up: bool = False
    ) -> str:
        how = "said (voice)" if turn.channel is InputChannel.VOICE else "typed in chat"
        parts = [
            self.memory.prompt_context(turn.speaker_id),
            "",
            f'Latest message - {turn.speaker_id} {how}: "{turn.text}"',
        ]
        last_answer = self._last_bot_answer() if follow_up else None
        if last_answer is not None:
            # Quote the exact answer being followed up on. A general "use the most recent
            # topic" rule alone let the model blend in older topics (seen in live tests).
            parts.append(
                f"This is a follow-up to the last answer, by {last_answer.speaker}: "
                f'"{last_answer.text}". Apply the request to that answer only.'
            )
        if already_answered:
            names = " and ".join(PERSONAS[p].display_name for p in already_answered)
            parts.append(
                f"{names} has already answered above. Do only the part the user asked of you, "
                "and do not repeat that answer."
            )
        parts.append("Reply now, speaking to the room.")
        return "\n".join(parts)

    def _finish(self, timer: TurnTimer, outcome: str) -> None:
        """Log the reply's latency line and publish it as a turn_done event."""
        self._emit("turn_done", **timer.emit(_log, outcome=outcome))

    def _emit(self, event: str, **fields: Any) -> None:
        """Hand an event to the room. A publishing problem must never break a turn."""
        if self._event_sink is None:
            return
        try:
            self._event_sink({"event": event, **fields})
        except Exception as exc:
            _log.warning("event_publish_failed", extra={"error": type(exc).__name__})

    def _last_bot_answer(self) -> MemoryTurn | None:
        for past in reversed(self.memory.turns):
            if past.persona is not None and past.text != INTERRUPTED_MARKER:
                return past
        return None

    def _maybe_text(self, text: str) -> dict[str, str]:
        """Conversation text is logged only when ROXSTAR_LOG_TRANSCRIPTS is on (demo/debug)."""
        return {"text": text} if self._log_transcripts else {}


def _describe(exc: BaseException) -> str:
    """Error type plus a short message; our LLMError lists which model failed and how."""
    return f"{type(exc).__name__}: {exc}"[:200] if str(exc) else type(exc).__name__
