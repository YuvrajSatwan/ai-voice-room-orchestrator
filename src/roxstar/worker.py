"""LiveKit worker: one job per room wires up the brain, the listener, and both bots.

    python -m roxstar.worker dev

What joins the room:
- the job's own connection  = the room brain (listens, never speaks, hidden in the UI)
- ai-dost                    = Kabir's voice + chat (male, Sarvam "shubh")
- ai-sathi                   = Saraah's voice + chat (female, Sarvam "simran")
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Callable

import livekit.plugins.sarvam as sarvam
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli

from roxstar.brain import RoomBrain
from roxstar.config import AGENT_NAME, Settings
from roxstar.domain import InputChannel, Persona
from roxstar.listener import RoomListener, is_human
from roxstar.llm import create_text_fn, reply_fn_from
from roxstar.log import configure_logging, get_logger
from roxstar.moderation import mask
from roxstar.personas import PERSONAS, PersonaConfiguration
from roxstar.voices import BotVoice, bot_token

_log = get_logger("worker")


def make_tts(persona: PersonaConfiguration, settings: Settings) -> sarvam.TTS:
    return sarvam.TTS(
        model=persona.voice.model,
        speaker=persona.voice.speaker,
        target_language_code=persona.voice.language_code,
        pace=persona.voice.pace,
        speech_sample_rate=24_000,
        api_key=settings.sarvam_api_key,
    )


def make_stt(settings: Settings) -> sarvam.STT:
    return sarvam.STT(
        language="hi-IN",
        model=settings.stt_model,
        mode=settings.stt_mode,
        api_key=settings.sarvam_api_key,
    )


# How long a room keeps its bots with no humans in it (covers a page refresh or a quick
# rejoin). After that the job ends, so abandoned rooms don't hold bots and memory forever.
EMPTY_ROOM_GRACE_S = 90.0


class EmptyRoomWatch:
    """Calls ``on_empty`` once the room has had no humans for ``grace_s`` seconds.

    ``check()`` is called whenever someone joins or leaves (and once at start, since the
    first human connects a moment after the bots are dispatched). A human arriving during
    the grace period cancels it.
    """

    def __init__(
        self,
        has_humans: Callable[[], bool],
        on_empty: Callable[[], None],
        *,
        grace_s: float = EMPTY_ROOM_GRACE_S,
    ) -> None:
        self._has_humans = has_humans
        self._on_empty = on_empty
        self._grace_s = grace_s
        self._timer: asyncio.TimerHandle | None = None

    def check(self) -> None:
        if self._has_humans():
            self.cancel()
        elif self._timer is None:
            self._timer = asyncio.get_running_loop().call_later(self._grace_s, self._expire)

    def cancel(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _expire(self) -> None:
        self._timer = None
        if not self._has_humans():
            self._on_empty()


def parse_chat(packet: rtc.DataPacket) -> str | None:
    """Return the text of a human chat message, or None for anything else."""
    if packet.participant is None or not is_human(packet.participant):
        return None  # bots' own replies must never come back in as new turns
    try:
        message = json.loads(packet.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(message, dict) or message.get("type") != "roxstar.chat":
        return None
    text = str(message.get("text", "")).strip()
    return text or None


async def entrypoint(ctx: JobContext) -> None:
    settings = Settings.from_environment(require_livekit=True)
    configure_logging(level=settings.log_level, log_format=settings.log_format)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await ctx.room.local_participant.set_attributes({"roxstar.role": "brain"})
    _log.info("brain_joined", extra={"room": ctx.room.name})

    bots: dict[Persona, BotVoice] = {}
    for persona, cfg in PERSONAS.items():
        voice = BotVoice(cfg, make_tts(cfg, settings))
        token = bot_token(
            persona=cfg,
            room=ctx.room.name,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
        await voice.connect(settings.livekit_url, token)
        bots[persona] = voice

    background: set[asyncio.Task[None]] = set()

    def publish_event(event: dict[str, object]) -> None:
        """Brain events -> a 'roxstar.event' data message the UI reads (never any secrets)."""
        payload = json.dumps({"type": "roxstar.event", "at": time.time(), **event})
        task = asyncio.create_task(ctx.room.local_participant.publish_data(payload, reliable=True))
        background.add(task)
        task.add_done_callback(background.discard)

    text_fn = create_text_fn(settings)  # one Gemini client for replies and summaries
    brain = RoomBrain(
        bots=bots,
        reply_fn=reply_fn_from(text_fn),
        summarize_fn=text_fn,
        room_name=ctx.room.name,
        log_transcripts=settings.log_transcripts,
        event_sink=publish_event,
    )

    async def post_system_note(text: str) -> None:
        payload = {"type": "roxstar.chat", "sender": "Room system", "text": text, "channel": "text"}
        with contextlib.suppress(Exception):
            await ctx.room.local_participant.publish_data(json.dumps(payload), reliable=True)

    async def show_transcript(speaker: str, text: str) -> None:
        """Post a human's spoken words to the chat so everyone sees what was heard."""
        participant = ctx.room.remote_participants.get(speaker)
        payload = {
            "type": "roxstar.chat",
            "sender": (participant.name if participant else "") or speaker,
            "identity": speaker,
            "text": mask(text.strip()),  # moderation: slurs never shown in the transcript
            "channel": "voice",
        }
        try:
            await ctx.room.local_participant.publish_data(json.dumps(payload), reliable=True)
        except Exception as exc:
            _log.warning("transcript_publish_failed", extra={"error": type(exc).__name__})

    listener = RoomListener(
        ctx.room, brain, make_stt(settings), show_transcript, event_sink=publish_event
    )
    listener.start()

    @ctx.room.on("data_received")
    def on_data(packet: rtc.DataPacket) -> None:
        text = parse_chat(packet)
        if not text or packet.participant is None:
            return
        if settings.demo_controls and text.startswith("/fail"):
            stage = text.removeprefix("/fail").strip().lower()
            armed = brain.simulate_failure(stage)
            note = (
                f"Demo: the next {stage.upper()} call will fail on purpose."
                if armed
                else "Demo: use /fail llm or /fail tts."
            )
            asyncio.create_task(post_system_note(note))
            return
        if text:
            brain.submit_turn(
                speaker=packet.participant.identity, text=text, channel=InputChannel.TEXT
            )

    def close_empty_room() -> None:
        _log.info("room_empty_shutdown", extra={"room": ctx.room.name})
        ctx.shutdown(reason="no humans left in the room")

    empty_watch = EmptyRoomWatch(
        lambda: any(is_human(p) for p in ctx.room.remote_participants.values()),
        close_empty_room,
    )
    empty_watch.check()

    @ctx.room.on("participant_connected")
    def on_join(participant: rtc.RemoteParticipant) -> None:
        _log.info("participant_joined", extra={"participant": participant.identity})
        empty_watch.check()

    @ctx.room.on("participant_disconnected")
    def on_leave(participant: rtc.RemoteParticipant) -> None:
        _log.info("participant_left", extra={"participant": participant.identity})
        empty_watch.check()

    async def shutdown() -> None:
        empty_watch.cancel()
        await listener.aclose()
        for voice in bots.values():
            await voice.aclose()

    ctx.add_shutdown_callback(shutdown)


def main() -> None:
    settings = Settings.from_environment(require_livekit=False)
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=AGENT_NAME,
            # Production defaults assume a big machine: 4 pre-started job processes (runs a
            # 512 MB host out of memory) and "full" at 70% CPU (a small shared CPU sits above
            # that, so LiveKit stops sending rooms). Start jobs on demand, never refuse rooms.
            num_idle_processes=0,
            load_threshold=float("inf"),
        )
    )


if __name__ == "__main__":
    main()
