"""Who is being addressed: the bots' names, as speech-to-text actually spells them.

The display names never change (Kabir, Saraah). What varies is the transcript: STT writes
Hinglish in Roman or Devanagari, and "Saraah" comes back as Sara, Saara, Sarah, सारा...
This module is the one place that knows those spellings; routing just asks
``addressed_bots(text)``.

Kabir     kabir, kabeer, kabira, कबीर                  a name wherever it appears
Saraah    saraah, sarah, sarahh, sarha, साराह, सारह     a name wherever it appears
          sara, saara, saraa, सारा                      ONLY when used to address someone:
                                                        at the start of a sentence or clause
                                                        ("Sara, ...", "Arre Saara ..."), or as
                                                        "AI Sara". In Hindi "saara/sara" also
                                                        means "whole" ("sara kaam", "सारा दिन"),
                                                        so mid-sentence it is not a name.

The assignment's original names still work when used as an address ("AI Dost, ...",
"AI Sathi, ..."), so its own test sentences route correctly. A bare "dost"/"saathi" is an
ordinary word ("mera dost aaya hai") and is ignored.
"""

from __future__ import annotations

import re

from roxstar.domain import Persona

# Devanagari letters and vowel signs, but not the danda (।), which ends a sentence.
_DEV = "ऀ-ॣ०-ॿ"


def _roman(words: str) -> str:
    return rf"(?<![a-z])(?:{words})(?![a-z])"


def _devanagari(words: str) -> str:
    return rf"(?<![{_DEV}])(?:{words})(?![{_DEV}])"


# Start of the text or of a clause, then optional "arre / hey / ok / AI ..." fillers.
_CLAUSE_START = r"(?:^|[,.!?।;:]\s*)"
_FILLERS = (
    r"(?:(?:arre|are|arey|hey|hi|hello|ok|okay|acha|achha|accha|suno|haan|han|ai|"
    r"अरे|हे|हाय|हेलो|सुनो|एआई)[\s,!.।]*)*"
)
# "Saara din", "sara kaam", "सारा पैसा": the Hindi word "whole", not the name.
_WHOLE_OF = (
    r"(?![\s,]+(?:din|raat|kaam|time|samay|paisa|paise|ghar|khana|mamla|maamla|saal|hafta|"
    r"mahina|sab|kuch|duniya|desh|shahar|data|code|pani|maal|दिन|रात|काम|समय|पैसा|पैसे|घर|"
    rf"खाना|मामला|साल|हफ्ता|महीना|सब|कुछ|दुनिया|देश|पानी)(?![a-z{_DEV}]))"
)
_SARA_LOOSE = _roman(r"saa?raa?") + "|" + _devanagari("सारा")

_ALWAYS: dict[Persona, re.Pattern[str]] = {
    Persona.DOST: re.compile(
        _roman(r"kabir|kabeer|kabira") + "|" + _devanagari("कबीर")
        # the assignment's original name, only as an address
        + r"|(?<![a-z])ai\s*(?:dost|दोस्त)(?![a-z])|एआई\s*दोस्त",
        re.IGNORECASE,
    ),
    Persona.SATHI: re.compile(
        _roman(r"saraa?h+|sarha|saaraah") + "|" + _devanagari("साराह|सारह")
        + r"|(?<![a-z])ai\s*(?:saa?thi|साथी)(?![a-z])|एआई\s*साथी",
        re.IGNORECASE,
    ),
}
_SARA_AS_ADDRESS = re.compile(
    rf"{_CLAUSE_START}{_FILLERS}(?P<name>{_SARA_LOOSE}){_WHOLE_OF}"
    rf"|(?<![a-z])ai\s+(?P<ai_name>{_roman(r'saa?raa?')})",
    re.IGNORECASE,
)


def _first_mention(persona: Persona, text: str) -> int | None:
    positions = [m.start() for m in _ALWAYS[persona].finditer(text)]
    if persona is Persona.SATHI:
        positions += [
            m.start("name") if m.group("name") else m.start("ai_name")
            for m in _SARA_AS_ADDRESS.finditer(text)
        ]
    return min(positions) if positions else None


def addressed_bots(text: str) -> tuple[Persona, ...]:
    """The bots addressed by name in ``text``, in the order they are mentioned."""
    hits = [
        (position, persona)
        for persona in (Persona.DOST, Persona.SATHI)
        if (position := _first_mention(persona, text)) is not None
    ]
    return tuple(persona for _, persona in sorted(hits))


# A fragment that is nothing but a way of calling a bot ("Kabir,", "हेलो सारा।"): the speaker
# paused and the question is still coming. Used by the utterance merger.
_ONLY_A_CALL = re.compile(
    r"^(?:(?:hey|hi|hello|suno|arre|ai|roxstar|kabir|kabeer|saraa?h*|saa?raa?|sarha|dost|"
    r"saa?thi|हेलो|सुनो|अरे|कबीर|साराह|सारह|सारा|दोस्त|साथी|एआई)[\s,।.!]*)+$",
    re.IGNORECASE,
)


def is_only_a_call(text: str) -> bool:
    return bool(_ONLY_A_CALL.match(text.strip()))
