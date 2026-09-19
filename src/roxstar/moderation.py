"""Basic moderation: catch clearly abusive words before they reach the LLM or the chat.

A word list, not a classifier: instant, free, predictable, and it covers the common Hindi,
Hinglish and English slurs in both Roman and Devanagari script. Mild words ("pagal",
"bakwas", "stupid") are deliberately not on it, since friends say them all the time.

An abusive turn never goes to the LLM. The bot answers with a calm fixed line, the words are
masked in the chat transcript, and memory keeps only the masked version.
"""

from __future__ import annotations

import re

from roxstar.domain import Persona

_ABUSIVE = re.compile(
    r"\b(?:chutiy[aeo]|madarchod|maderchod|behe?nchod|bhenchod|bhanchod|bsdk|"
    r"bhosdi(?:ke|wale)?|bhosadi(?:ke)?|gaa?ndu|lodu|lawde|lavde|randi|harami|haramzad[ae]|"
    r"kamin[ae]|fuck(?:ing|er)?|motherfucker|bitch|bastard|asshole|dickhead)\b"
    r"|चूतिय[ाे]|मादरचोद|बहनचोद|भोसड़ी|गांडू|रंडी|हरामी|हरामज़ाद[ाे]|कमीन[ाे]",
    re.IGNORECASE,
)

WARNING_LINES = {
    Persona.DOST: "Arre yaar, thoda respect se baat karte hain. Main help ke liye hoon, "
    "apna sawaal poochho.",
    Persona.SATHI: "Hey, bina gaali ke baat karte hain na. Aap apna sawaal poochiye, "
    "main help karti hoon.",
}


def is_abusive(text: str) -> bool:
    return bool(_ABUSIVE.search(text))


def mask(text: str) -> str:
    return _ABUSIVE.sub("***", text)
