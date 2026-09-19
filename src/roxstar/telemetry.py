"""Per-response latency: one log line per bot reply with the time spent in each stage.

The clock starts when the final transcript (or chat message) reaches the brain, so
``first_audio_ms`` is the delay a user actually feels between finishing a sentence
and hearing the bot start to reply (plus the STT finalisation time, logged by Sarvam).
"""

from __future__ import annotations

import logging
from time import monotonic


class TurnTimer:
    def __init__(
        self, *, turn_id: str, speaker: str, channel: str, bot: str, started_at: float | None = None
    ) -> None:
        self._fields: dict[str, object] = {
            "turn_id": turn_id,
            "speaker": speaker,
            "channel": channel,
            "bot": bot,
        }
        self._start = started_at if started_at is not None else monotonic()

    def mark(self, stage: str) -> None:
        """Record ``<stage>_ms`` since the turn arrived. First mark of a stage wins."""
        self._fields.setdefault(f"{stage}_ms", round((monotonic() - self._start) * 1000))

    def emit(self, logger: logging.Logger, *, outcome: str) -> dict[str, object]:
        self.mark("total")
        self._fields["outcome"] = outcome
        logger.info("turn_latency", extra=self._fields)
        return dict(self._fields)
