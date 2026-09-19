"""LLM reply generation with Gemini. The brain only sees ``reply(persona, prompt) -> text``.

Models: ``gemini-3.5-flash-lite`` first (no hidden "thinking", natural Hinglish), then
``gemini-flash-lite-latest`` as the fallback (a different model, so a separate capacity pool).

Failover, per turn:
- each model gets ``per_model_timeout_s``; on an error or timeout, the next model is tried;
- a model that just failed is skipped for ``cooldown_s``, so when Gemini is overloaded (503)
  every user doesn't wait for the same failure again;
- only if every model fails does the brain speak its apology line.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from time import monotonic

from google import genai
from google.genai import types

from roxstar.config import ConfigurationError, Settings
from roxstar.log import get_logger
from roxstar.personas import PersonaConfiguration

ReplyFn = Callable[[PersonaConfiguration, str], Awaitable[str]]
TextFn = Callable[[str, str], Awaitable[str]]  # (system instruction, prompt) -> text

_log = get_logger("llm")
# Spoken length is set by the persona prompt ("1 to 3 sentences"). This cap is only a
# safety net, and is high enough that a thinking model's hidden tokens can't truncate a reply.
_MAX_TOKENS = 1024
_TEMPERATURE = 0.7


class LLMError(RuntimeError):
    """Every model failed, or returned nothing usable."""


def create_text_fn(settings: Settings) -> TextFn:
    """One Gemini client (and one failover state) shared by replies and summaries."""
    if not settings.gemini_api_key:
        raise ConfigurationError("GEMINI_API_KEY is required")
    models = [settings.gemini_model]
    if settings.gemini_fallback_model and settings.gemini_fallback_model not in models:
        models.append(settings.gemini_fallback_model)
    return gemini_text_fn(api_key=settings.gemini_api_key, models=models)


def create_reply_fn(settings: Settings) -> ReplyFn:
    return reply_fn_from(create_text_fn(settings))


def reply_fn_from(text_fn: TextFn) -> ReplyFn:
    async def reply(persona: PersonaConfiguration, prompt: str) -> str:
        return await text_fn(persona.instructions(), prompt)

    return reply


def gemini_reply_fn(*, api_key: str, models: Sequence[str], **options: float) -> ReplyFn:
    return reply_fn_from(gemini_text_fn(api_key=api_key, models=models, **options))


def gemini_text_fn(
    *,
    api_key: str,
    models: Sequence[str],
    per_model_timeout_s: float = 5.0,
    cooldown_s: float = 60.0,
) -> TextFn:
    client = genai.Client(api_key=api_key)
    failed_at: dict[str, float] = {}

    def in_cooldown(model: str) -> bool:
        return monotonic() - failed_at.get(model, -cooldown_s) < cooldown_s

    async def generate(system: str, prompt: str) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=_TEMPERATURE,
            max_output_tokens=_MAX_TOKENS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        # Healthy models first; cooling-down ones are still tried last rather than never.
        order = sorted(models, key=in_cooldown)
        errors: list[str] = []
        for model in order:
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(model=model, contents=prompt, config=config),
                    per_model_timeout_s,
                )
                text = (response.text or "").strip()
                if not text:
                    raise LLMError("empty reply")
            except Exception as exc:
                failed_at[model] = monotonic()
                errors.append(f"{model}: {type(exc).__name__} {getattr(exc, 'code', '')}".strip())
                continue
            if errors:
                _log.warning("llm_failover_used", extra={"model": model, "failed": errors})
            return text
        raise LLMError("; ".join(errors))

    return generate
