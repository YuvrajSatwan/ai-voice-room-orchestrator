"""Speech-to-text going down (e.g. provider out of credits): back off, tell the room, recover."""

from types import SimpleNamespace

import pytest

from roxstar import listener as listener_module
from roxstar.listener import RoomListener, retry_delay


def test_retry_delay_backs_off_then_caps() -> None:
    assert [retry_delay(n) for n in range(1, 8)] == [2, 4, 8, 16, 30, 30, 30]


def make_listener(events: list[dict]) -> RoomListener:
    dummy = SimpleNamespace()
    return RoomListener(room=dummy, brain=dummy, stt=dummy, event_sink=events.append)


async def test_failures_back_off_publish_events_and_recover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict] = []
    listener = make_listener(events)
    attempts = 0

    async def run_stream(speaker, track):
        nonlocal attempts
        attempts += 1
        if attempts <= 4:
            raise RuntimeError("402 no credits")
        listener._heard(speaker)  # credits topped up: speech gets through again

    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    listener._run_stream = run_stream  # type: ignore[method-assign]
    monkeypatch.setattr(listener_module.asyncio, "sleep", fake_sleep)
    await listener._listen("Rahul", track=None)

    assert sleeps == [2, 4, 8, 16]
    assert [e["event"] for e in events] == ["stt_failed"] * 4 + ["stt_recovered"]
    assert events[3] == {
        "event": "stt_failed",
        "speaker": "Rahul",
        "error": "RuntimeError",
        "attempt": 4,
        "retry_in_s": 16,
    }
    assert events[4] == {"event": "stt_recovered", "speaker": "Rahul"}


async def test_speech_without_a_prior_failure_publishes_nothing() -> None:
    events: list[dict] = []
    make_listener(events)._heard("Rahul")
    assert events == []


async def test_a_broken_event_sink_never_stops_listening(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(_event: dict) -> None:
        raise RuntimeError("room gone")

    dummy = SimpleNamespace()
    listener = RoomListener(room=dummy, brain=dummy, stt=dummy, event_sink=explode)
    calls = 0

    async def run_stream(speaker, track):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("blip")

    async def fake_sleep(_delay: float) -> None:
        return None

    listener._run_stream = run_stream  # type: ignore[method-assign]
    monkeypatch.setattr(listener_module.asyncio, "sleep", fake_sleep)
    await listener._listen("Rahul", track=None)
    assert calls == 2
