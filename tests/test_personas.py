import pytest

from roxstar.personas import AI_DOST, AI_SATHI, PERSONAS, STYLE_EXAMPLES

BOTH = pytest.mark.parametrize("persona", [AI_DOST, AI_SATHI], ids=["dost", "sathi"])


def test_two_distinct_identities_and_voices() -> None:
    assert (AI_DOST.livekit_identity, AI_SATHI.livekit_identity) == ("ai-dost", "ai-sathi")
    assert AI_DOST.voice.speaker == "shubh"  # male Bulbul voice
    assert AI_SATHI.voice.speaker == "simran"  # female Bulbul voice
    assert {p.voice.language_code for p in PERSONAS.values()} == {"hi-IN"}


@BOTH
def test_prompt_asks_for_hinglish_even_for_english_questions(persona) -> None:
    prompt = persona.instructions()
    assert "Reply in Hinglish even when the question is in English" in prompt
    assert "Use full English only if someone asks" in prompt


@BOTH
def test_prompt_carries_the_assignment_style_benchmark(persona) -> None:
    prompt = persona.instructions()
    for formal, natural in STYLE_EXAMPLES:
        assert f'Say "{natural}", not "{formal}"' in prompt


@BOTH
def test_prompt_keeps_spoken_replies_short_and_plain(persona) -> None:
    prompt = persona.instructions()
    assert "1 to 3 sentences" in prompt
    assert "no markdown" in prompt


def test_each_bot_speaks_with_its_own_grammatical_gender() -> None:
    assert "main batata hoon" in AI_DOST.instructions()
    assert "main batati hoon" in AI_SATHI.instructions()
    assert "main batati hoon" not in AI_DOST.instructions()
