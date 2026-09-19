"""Hears every human in the room: one speech-to-text stream per human microphone.

Why one stream per human (instead of LiveKit's AgentSession)? AgentSession listens to a
single linked participant, but this room has several humans. A separate stream per mic
also gives exact speaker attribution for free: we know whose track the audio came from.

Sarvam's streaming STT runs voice-activity detection on its side and sends:
- START_OF_SPEECH  -> ``brain.on_user_started_speaking`` (barge-in)
- FINAL_TRANSCRIPT -> collected by ``UtteranceMerger``, then one turn goes to the brain and
                    to the room chat

Why merge? People pause mid-sentence. "AI Sathi, [pause] cloud kya hai?" arrives as two
finals, and without merging "AI Sathi" becomes its own turn and the question goes to the
wrong bot (seen in live testing).

If a stream fails (network, provider down, out of credits) it is restarted with an
exponential back-off (2, 4, 8, 16, 30 s) so a dead provider isn't hammered. Each failure is
published as an `stt_failed` room event and the first speech after it as `stt_recovered`,
so the UI can tell a person their voice isn't getting through. The room keeps running and
other speakers are unaffected.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from livekit import rtc
from livekit.agents import stt as lk_stt

from roxstar.brain import RoomBrain
from roxstar.domain import InputChannel
from roxstar.log import get_logger

_log = get_logger("listener")
_SAMPLE_RATE = 16_000
_RETRY_BASE_S = 2.0
_RETRY_MAX_S = 30.0
# A stream that ran this long before failing was healthy: start the back-off over.
_HEALTHY_AFTER_S = 15.0


def retry_delay(failures: int) -> float:
    """2, 4, 8, 16, then 30 s forever: fast recovery from blips, gentle on a dead provider."""
    return min(_RETRY_MAX_S, _RETRY_BASE_S * 2 ** max(0, failures - 1))


# A fragment that is only a bot's name, or ends mid-thought, is clearly not the whole turn.
_UNFINISHED = re.compile(
    r"^(?:(?:hey|hi|hello|suno|ai|roxstar|dost|saa?thi|दोस्त|साथी|एआई)[\s,।.!]*)+$"
    r"|(?:,|\b(?:aur|ki|ke|ko|to|toh|and|but|or)|(?:^|\s)(?:और|कि|तो))[\s।.]*$",
    re.IGNORECASE,
)


class UtteranceMerger:
    """Joins one speaker's back-to-back STT finals into a single turn.

    After a final transcript it waits ``hold_s`` (longer if the text is clearly unfinished)
    for the speaker to continue. If they start speaking again, it keeps waiting for the
    next final; ``max_wait_s`` is a safety net if that final never comes.
    """

    def __init__(
        self,
        deliver: Callable[[str], None],
        *,
        hold_s: float = 0.7,
        unfinished_hold_s: float = 2.0,
        max_wait_s: float = 6.0,
    ) -> None:
        self._deliver = deliver
        self._hold_s = hold_s
        self._unfinished_hold_s = unfinished_hold_s
        self._max_wait_s = max_wait_s
        self._parts: list[str] = []
        self._timer: asyncio.TimerHandle | None = None

    def speech_started(self) -> None:
        if self._parts:
            self._schedule(self._max_wait_s)  # they're still talking: wait for the next final

    def final(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._parts.append(text)
        unfinished = _UNFINISHED.search(" ".join(self._parts))
        self._schedule(self._unfinished_hold_s if unfinished else self._hold_s)

    def flush(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._parts:
            text = " ".join(self._parts)
            self._parts.clear()
            self._deliver(text)

    def _schedule(self, delay: float) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = asyncio.get_running_loop().call_later(delay, self.flush)


def is_human(participant: rtc.RemoteParticipant) -> bool:
    return participant.kind != rtc.ParticipantKind.PARTICIPANT_KIND_AGENT


class RoomListener:
    def __init__(
        self,
        room: rtc.Room,
        brain: RoomBrain,
        stt: lk_stt.STT,
        show_transcript: Callable[[str, str], Awaitable[None]] | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._room = room
        self._brain = brain
        self._stt = stt
        self._show_transcript = show_transcript
        self._event_sink = event_sink
        self._failures: dict[str, int] = {}  # consecutive STT failures per speaker
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._chat_tasks: set[asyncio.Task[None]] = set()

    def start(self) -> None:
        self._room.on("track_subscribed", self._on_track_subscribed)
        self._room.on("track_unsubscribed", self._on_track_gone)
        self._room.on("participant_disconnected", self._on_participant_gone)
        for participant in self._room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.track is not None:
                    self._on_track_subscribed(publication.track, publication, participant)

    async def aclose(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    def _on_track_subscribed(
        self,
        track: rtc.Track,
        _publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO or not is_human(participant):
            return
        speaker = participant.identity
        self._stop(speaker)  # a reconnect replaces the old stream
        self._tasks[speaker] = asyncio.create_task(self._listen(speaker, track))
        _log.info("listening", extra={"speaker": speaker})

    def _on_track_gone(
        self,
        track: rtc.Track,
        _publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            self._stop(participant.identity)

    def _on_participant_gone(self, participant: rtc.RemoteParticipant) -> None:
        self._stop(participant.identity)

    def _stop(self, speaker: str) -> None:
        task = self._tasks.pop(speaker, None)
        if task is not None:
            task.cancel()
            _log.info("stopped_listening", extra={"speaker": speaker})

    def _post_to_chat(self, speaker: str, text: str) -> None:
        """Show what a human said in the chat. Failing to post never blocks the turn."""
        if self._show_transcript is None:
            return
        task = asyncio.create_task(self._show_transcript(speaker, text))
        self._chat_tasks.add(task)
        task.add_done_callback(self._chat_tasks.discard)

    def _emit(self, event: str, **fields: Any) -> None:
        """Publish a room event. Never lets a publishing problem touch the audio path."""
        if self._event_sink is None:
            return
        try:
            self._event_sink({"event": event, **fields})
        except Exception as exc:
            _log.warning("event_publish_failed", extra={"error": type(exc).__name__})

    def _heard(self, speaker: str) -> None:
        """Speech got through: if this speaker's STT had been failing, it has recovered."""
        if self._failures.pop(speaker, 0):
            _log.info("stt_recovered", extra={"speaker": speaker})
            self._emit("stt_recovered", speaker=speaker)

    async def _listen(self, speaker: str, track: rtc.Track) -> None:
        """Keep one STT stream alive for this speaker, restarting it with back-off if it fails."""
        while True:
            started = monotonic()
            try:
                await self._run_stream(speaker, track)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if monotonic() - started > _HEALTHY_AFTER_S:
                    self._failures[speaker] = 0  # it was working; this is a fresh problem
                failures = self._failures.get(speaker, 0) + 1
                self._failures[speaker] = failures
                delay = retry_delay(failures)
                _log.warning(
                    "stt_stream_failed",
                    extra={
                        "speaker": speaker,
                        "error": type(exc).__name__,
                        "attempt": failures,
                        "retry_in_s": delay,
                    },
                )
                self._emit(
                    "stt_failed",
                    speaker=speaker,
                    error=type(exc).__name__,
                    attempt=failures,
                    retry_in_s=delay,
                )
                await asyncio.sleep(delay)

    async def _run_stream(self, speaker: str, track: rtc.Track) -> None:
        audio = rtc.AudioStream(track, sample_rate=_SAMPLE_RATE, num_channels=1)
        stt_stream = self._stt.stream()

        async def pump_audio() -> None:
            async for event in audio:
                stt_stream.push_frame(event.frame)
            stt_stream.end_input()

        def deliver(text: str) -> None:
            self._post_to_chat(speaker, text)
            self._brain.submit_turn(speaker=speaker, text=text, channel=InputChannel.VOICE)

        merger = UtteranceMerger(deliver)
        pump = asyncio.create_task(pump_audio())
        try:
            async for event in stt_stream:
                if event.type == lk_stt.SpeechEventType.START_OF_SPEECH:
                    self._heard(speaker)
                    merger.speech_started()
                    self._brain.on_user_started_speaking(speaker)
                elif event.type == lk_stt.SpeechEventType.FINAL_TRANSCRIPT and event.alternatives:
                    self._heard(speaker)
                    merger.final(event.alternatives[0].text)
        finally:
            merger.flush()  # don't lose words said just before the stream closed
            pump.cancel()
            await stt_stream.aclose()
            await audio.aclose()
