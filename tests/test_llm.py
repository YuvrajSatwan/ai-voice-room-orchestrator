from types import SimpleNamespace

import pytest

from roxstar import llm
from roxstar.llm import LLMError, gemini_reply_fn
from roxstar.personas import AI_DOST


def fake_client(behaviour: dict[str, object]):
    """A stand-in genai.Client: each model either raises or returns the given text."""
    calls: list[str] = []

    async def generate_content(*, model, contents, config):
        calls.append(model)
        outcome = behaviour[model]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    return client, calls


async def test_falls_back_to_the_lighter_model_when_the_main_one_is_overloaded(monkeypatch):
    client, calls = fake_client({"flash": RuntimeError("503"), "lite": "Theek hai, suno."})
    monkeypatch.setattr(llm.genai, "Client", lambda api_key: client)
    reply = gemini_reply_fn(api_key="k", models=["flash", "lite"])
    assert await reply(AI_DOST, "prompt") == "Theek hai, suno."
    assert calls == ["flash", "lite"]


async def test_main_model_answers_without_touching_the_fallback(monkeypatch):
    client, calls = fake_client({"flash": "  AI ek technology hai.  ", "lite": "unused"})
    monkeypatch.setattr(llm.genai, "Client", lambda api_key: client)
    reply = gemini_reply_fn(api_key="k", models=["flash", "lite"])
    assert await reply(AI_DOST, "prompt") == "AI ek technology hai."
    assert calls == ["flash"]


async def test_raises_when_every_model_fails_or_is_empty(monkeypatch):
    client, _ = fake_client({"flash": RuntimeError("503"), "lite": "   "})
    monkeypatch.setattr(llm.genai, "Client", lambda api_key: client)
    reply = gemini_reply_fn(api_key="k", models=["flash", "lite"])
    with pytest.raises(LLMError, match="flash.*lite"):
        await reply(AI_DOST, "prompt")


async def test_a_failed_model_is_skipped_during_its_cooldown(monkeypatch):
    client, calls = fake_client({"lite": RuntimeError("503"), "flash": "Haan bilkul."})
    monkeypatch.setattr(llm.genai, "Client", lambda api_key: client)
    reply = gemini_reply_fn(api_key="k", models=["lite", "flash"], cooldown_s=60)
    await reply(AI_DOST, "first")
    await reply(AI_DOST, "second")
    assert calls == ["lite", "flash", "flash"]  # second turn goes straight to the healthy model


async def test_a_slow_model_times_out_and_the_next_one_answers(monkeypatch):
    import asyncio

    async def slow(*, model, contents, config):
        if model == "lite":
            await asyncio.sleep(5)
        return SimpleNamespace(text="Jaldi wala jawab.")

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=slow)))
    monkeypatch.setattr(llm.genai, "Client", lambda api_key: client)
    reply = gemini_reply_fn(api_key="k", models=["lite", "flash"], per_model_timeout_s=0.05)
    assert await reply(AI_DOST, "prompt") == "Jaldi wala jawab."
