"""A bot's presence in the room: its own LiveKit participant, audio track, and chat sender.

Each bot joins with its own identity (``ai-dost`` / ``ai-sathi``, shown as Kabir / Saraah),
so the room shows two
separate AI participants and each voice comes from the right one. The brain decides *what*
and *when*; this class only turns text into audio on that bot's track.

Speaking is done sentence by sentence: while sentence 1 plays, sentence 2 is already being
synthesized. That cuts the wait before the first audio and makes barge-in fast, because
only the current sentence is queued when the user interrupts.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from typing import TypeVar

from livekit import api, rtc
from livekit.agents import tts as lk_tts

from roxstar.log import get_logger
from roxstar.personas import PersonaConfiguration, for_speech

_log = get_logger("voices")
_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")
_T = TypeVar("_T")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def bot_token(*, persona: PersonaConfiguration, room: str, api_key: str, api_secret: str) -> str:
    """Room-scoped token that makes the bot show up as an agent participant."""
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(persona.livekit_identity)
        .with_name(persona.display_name)
        .with_kind("agent")
        .with_attributes({"roxstar.role": "bot", "roxstar.persona": persona.identity.value})
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=False,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )


class BotVoice:
    def __init__(self, persona: PersonaConfiguration, tts: lk_tts.TTS) -> None:
        self.persona = persona
        self._tts = tts
        self._room = rtc.Room()
        self._source = rtc.AudioSource(tts.sample_rate, tts.num_channels)
        self._url: str = ""
        self._token: str = ""
        self._closed: bool = False
        self._setup_room_listeners()

    def _setup_room_listeners(self) -> None:
        @self._room.on("disconnected")
        def _on_disconnected(reason: object = None) -> None:
            _log.warning(
                "bot_disconnected",
                extra={"bot": self.persona.livekit_identity, "reason": str(reason)},
            )
            if not self._closed:
                asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        if self._closed or not self._url or not self._token:
            return
        await asyncio.sleep(1.0)
        if self._closed or self._room.isconnected():
            return
        _log.info("bot_reconnecting", extra={"bot": self.persona.livekit_identity})
        try:
            self._room = rtc.Room()
            self._setup_room_listeners()
            await self._room.connect(self._url, self._token, options=rtc.RoomOptions(auto_subscribe=False))
            track = rtc.LocalAudioTrack.create_audio_track("voice", self._source)
            await self._room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )
            _log.info("bot_reconnected", extra={"bot": self.persona.livekit_identity})
        except Exception as exc:
            _log.error(
                "bot_reconnect_failed",
                extra={"bot": self.persona.livekit_identity, "error": str(exc)},
            )

    async def connect(self, url: str, token: str) -> None:
        self._url = url
        self._token = token
        self._closed = False
        await self._room.connect(url, token, options=rtc.RoomOptions(auto_subscribe=False))
        track = rtc.LocalAudioTrack.create_audio_track("voice", self._source)
        await self._room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        _log.info("bot_joined", extra={"bot": self.persona.livekit_identity})

    async def aclose(self) -> None:
        self._closed = True
        await self._room.disconnect()

    async def post_text(self, text: str) -> None:
        if not self._room.isconnected():
            _log.warning("bot_not_connected_skip_chat", extra={"bot": self.persona.livekit_identity})
            return
        payload = {
            "type": "roxstar.chat",
            "sender": self.persona.display_name,
            "identity": self.persona.livekit_identity,
            "text": text,
            "channel": "voice",
        }
        await self._room.local_participant.publish_data(json.dumps(payload), reliable=True)

    async def speak(
        self, text: str, cancel: asyncio.Event, on_first_audio: Callable[[], None] | None = None
    ) -> bool:
        sentences = split_sentences(text) or [text]
        pending = asyncio.ensure_future(self._synthesize(sentences[0]))
        try:
            for index in range(len(sentences)):
                ok, frames = await _unless_cancelled(pending, cancel)
                if not ok:
                    return self._stop()
                if index + 1 < len(sentences):
                    pending = asyncio.ensure_future(self._synthesize(sentences[index + 1]))
                for frame in frames or []:
                    if cancel.is_set():
                        return self._stop()
                    await self._source.capture_frame(frame)
                    if on_first_audio:
                        on_first_audio()
                        on_first_audio = None
            ok, _ = await _unless_cancelled(
                asyncio.ensure_future(self._source.wait_for_playout()), cancel
            )
            return ok or self._stop()
        finally:
            if not pending.done():
                pending.cancel()

    async def _synthesize(self, sentence: str) -> list[rtc.AudioFrame]:
        async with self._tts.synthesize(for_speech(sentence)) as stream:
            return [chunk.frame async for chunk in stream]

    def _stop(self) -> bool:
        self._source.clear_queue()  # drop audio already queued so the bot goes quiet now
        return False


async def _unless_cancelled(
    work: asyncio.Future[_T], cancel: asyncio.Event
) -> tuple[bool, _T | None]:
    """Wait for ``work`` unless ``cancel`` fires first. Returns (finished, result)."""
    cancel_wait = asyncio.ensure_future(cancel.wait())
    try:
        await asyncio.wait({work, cancel_wait}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        cancel_wait.cancel()
    if cancel.is_set():
        work.cancel()
        return False, None
    return True, work.result()
