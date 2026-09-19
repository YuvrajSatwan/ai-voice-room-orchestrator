"""Checks for the 'natural Hinglish' rubric: used by the live style tests."""

from __future__ import annotations

import re

# Formal / textbook Hindi the assignment explicitly penalises (Roman spellings).
FORMAL_WORDS = (
    "kripya", "krupya", "takneek", "nirnay", "saksham", "pratiksha", "kaksh", "pravesh",
    "dhwanigrahak", "sakriya", "anubhav", "vishay", "prashn", "uttar dijiye", "sahayata",
    "avashya", "dhanyavaad", "prayog", "upyog", "madhyam", "vyakti", "atyant",
)  # fmt: skip

# Everyday Hindi glue words: an English-only reply contains none of these.
HINDI_GLUE = re.compile(
    r"\b(?:hai|hain|ka|ki|ke|mein|ko|se|aur|jo|toh|ye|yeh|woh|kya|karo|karta|karti|"
    r"hota|hoti|jaise|matlab|bhi|nahi|bas|ek|fir|phir|lo|dekh|dono|bhai|yaar|raha|rahe|"
    r"rahi|gaya|gayi|sakte|sakta|wala|wali|abhi|bahut|accha|achha|tum|aap|hum|main)\b",
    re.IGNORECASE,
)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_MARKDOWN = re.compile(r"(\*\*|^#|^\s*[-*•]\s|^\s*\d+\.\s)", re.MULTILINE)


def style_problems(text: str, *, max_words: int = 70) -> list[str]:
    problems = []
    lowered = text.lower()
    problems += [f"formal word: {w}" for w in FORMAL_WORDS if w in lowered]
    letters = [c for c in text if c.isalpha()]
    if letters and len(_DEVANAGARI.findall(text)) / len(letters) > 0.1:
        problems.append("not Roman script")
    if len(HINDI_GLUE.findall(text)) < 2:
        problems.append("not Hinglish (looks like pure English)")
    if len(text.split()) > max_words:
        problems.append(f"too long for voice: {len(text.split())} words")
    if _MARKDOWN.search(text):
        problems.append("markdown in a spoken reply")
    if re.search(r"\b(?:tune|tujhe|tera|teri)\b", lowered):
        problems.append('addresses someone as "tu" (use "tum")')
    if "useful detail" in lowered:
        problems.append("stock phrase: useful detail")
    return problems
