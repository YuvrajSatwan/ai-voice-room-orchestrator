"""Settings from environment variables. Errors name the missing variable, never its value."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv

# The worker registers under this name; the token server dispatches it into each room.
# Give a local run its own name (ROXSTAR_AGENT_NAME=roxstar-local) so a deployed worker on
# the same LiveKit project can't pick up your local rooms.
AGENT_NAME = getenv("ROXSTAR_AGENT_NAME", "").strip() or "roxstar"


class ConfigurationError(ValueError):
    """Required configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    sarvam_api_key: str | None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_fallback_model: str = "gemini-flash-lite-latest"
    stt_model: str = "saaras:v3"
    stt_mode: str = "codemix"
    log_level: str = "INFO"
    log_format: str = "json"
    log_transcripts: bool = False
    demo_controls: bool = False

    @classmethod
    def from_environment(cls, *, require_livekit: bool = True) -> Settings:
        load_dotenv()
        values = {
            "livekit_url": getenv("LIVEKIT_URL", "").strip(),
            "livekit_api_key": getenv("LIVEKIT_API_KEY", "").strip(),
            "livekit_api_secret": getenv("LIVEKIT_API_SECRET", "").strip(),
            "sarvam_api_key": getenv("SARVAM_API_KEY") or None,
            "gemini_api_key": getenv("GEMINI_API_KEY") or getenv("GOOGLE_API_KEY") or None,
            "gemini_model": getenv("GEMINI_MODEL", "").strip() or "gemini-3.5-flash-lite",
            "gemini_fallback_model": (
                getenv("GEMINI_FALLBACK_MODEL", "").strip() or "gemini-flash-lite-latest"
            ),
            "stt_model": getenv("SARVAM_STT_MODEL", "").strip() or "saaras:v3",
            "stt_mode": getenv("SARVAM_STT_MODE", "").strip() or "codemix",
            "log_level": getenv("ROXSTAR_LOG_LEVEL", "INFO").upper(),
            "log_format": getenv("ROXSTAR_LOG_FORMAT", "json").lower(),
            "log_transcripts": getenv("ROXSTAR_LOG_TRANSCRIPTS", "").lower() in {"1", "true"},
            "demo_controls": getenv("ROXSTAR_DEMO_CONTROLS", "").lower() in {"1", "true"},
        }
        if require_livekit:
            missing = [
                name
                for name in ("livekit_url", "livekit_api_key", "livekit_api_secret")
                if not values[name]
            ]
            if missing:
                names = ", ".join(name.upper() for name in missing)
                raise ConfigurationError(f"Missing required environment variables: {names}")
        if values["log_format"] not in {"json", "text"}:
            raise ConfigurationError("ROXSTAR_LOG_FORMAT must be 'json' or 'text'")
        return cls(**values)  # type: ignore[arg-type]
