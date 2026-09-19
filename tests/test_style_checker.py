"""The style checker itself must be right, or the live style tests prove nothing."""

import pytest
from style import style_problems


@pytest.mark.parametrize(
    "reply",
    [
        "AI ek aisi technology hai jo machine ko samajhne aur decision lene layak banati hai.",
        "Rahul bhai, Dilwale Dulhania Le Jayenge ya fir Chennai Express dekh lo. "
        "Dono hi zabardast hit movies hain.",
        "Ek second ruk jao, main check karta hoon.",
    ],
)
def test_natural_hinglish_passes(reply: str) -> None:
    assert style_problems(reply) == []


def test_formal_textbook_hindi_is_flagged() -> None:
    problems = style_problems("Kripya pratiksha karein, main aapki sahayata karunga.")
    assert {"formal word: kripya", "formal word: pratiksha", "formal word: sahayata"} <= set(
        problems
    )


def test_pure_english_is_flagged() -> None:
    reply = "Cloud computing means storing your files on remote servers over the internet."
    assert "not Hinglish (looks like pure English)" in style_problems(reply)


def test_devanagari_markdown_length_and_stock_phrases_are_flagged() -> None:
    assert "not Roman script" in style_problems("एआई एक तकनीक है जो मशीनों को सक्षम बनाती है")
    assert "markdown in a spoken reply" in style_problems("**AI** ek technology hai aur\n- ye")
    assert any(p.startswith("too long") for p in style_problems("ye bahut lamba hai " * 30))
    assert "stock phrase: useful detail" in style_problems("Ek useful detail ye hai ki...")
    assert 'addresses someone as "tu" (use "tum")' in style_problems(
        "Rahul, tune cricket ke baare mein poocha tha aur ye bataya tha."
    )
