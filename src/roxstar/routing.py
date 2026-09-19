"""Decides which bot (if any) answers a turn, using simple, explainable rules.

Rules, in order:
1. Named        - "AI Dost, ..." / "Sathi ..." -> that bot. Both named -> both, in the order
                  they were named (still one after another, never together).
2. Follow-up    - "uski", "simple batao", "yeh bahut lamba hai" right after a bot spoke
                  -> the bot that spoke last.
3. Answer       - the bot's last reply ended with a question ("Batao, kya discuss karna
                  hai?") and a human speaks right after -> that bot hears the answer,
                  even with no name or question words ("kuch bhi yaar, jo tum chaho").
4. Question     - an unnamed question or request ("AI kya hai?", "cloud samjhao") that is
                  not aimed at another human by name -> the bot already in the conversation,
                  or AI Dost if neither has spoken yet.
5. Otherwise    - silence. "ohh", "thank you", "mera naam Rahul hai", or Rahul talking to
                  Priya get no reply (they are still remembered).

Speech-to-text returns Hinglish in mixed script ("AI दोस्त, cloud क्या है"), so every rule
matches both Roman and Devanagari spellings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from roxstar.domain import Persona, ResponseDecision, UserTurn

_NAME_PATTERNS = {
    Persona.DOST: re.compile(r"\bdost\b|दोस्त", re.IGNORECASE),
    Persona.SATHI: re.compile(r"\bsaa?thi\b|साथी", re.IGNORECASE),
}

# Continue / reshape the bot's last answer.
_FOLLOW_UP = re.compile(
    r"\b(?:uska|uski|uske|unka|unki|unke|iska|iski|iske|wahi|wohi|same topic|"
    r"simple|aur batao|thoda aur|example|drawback|lamba|chhota|short mein|"
    r"samajh nahi|phir se|dobara|repeat|matlab|another|one more|ek aur|aur ek|"
    r"doosra|dusra|continue)\b"
    r"|उसका|उसकी|उसके|उनका|उनकी|उनके|इसका|इसकी|इसके|वही|सिंपल|और बताओ|थोड़ा और|"
    r"लंबा|छोटा|समझ नहीं|फिर से|दोबारा|मतलब|एक और|दूसरा",
    re.IGNORECASE,
)

# A question or a request for information.
_QUESTION = re.compile(
    r"\?|\b(?:kya|kaise|kaisa|kyun|kyon|kaun|kab|kahan|kitna|kitne|kaunsa|konsa|"
    r"batao|bataiye|batayiye|bata do|samjhao|samjhaiye|samjha do|suggest|"
    r"sunao|sunaiye|suna do|bolo|boliye|dikhao|"
    r"what|how|why|who|when|where|which|explain|tell me|tell us|give me|can you|could you|"
    r"define|summary|summarize|recap)\b"
    r"|क्या|कैसे|क्यों|कौन|कब|कहाँ|कहां|कितना|कितने|बताओ|बताइए|बताइये|समझाओ|समझाइए|"
    r"सुनाओ|सुनाइए|बोलो|बोलिए|दिखाओ|सारांश",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RoutingContext:
    """The little room state routing needs."""

    last_responder: Persona | None = None
    bot_spoke_recently: bool = False  # a bot reply is among the last few turns
    bot_asked_question: bool = False  # the last bot reply, just now, ended with a question
    other_humans: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ResponsePlan:
    """Ordered list of bots that should answer. Executed one at a time."""

    decisions: tuple[ResponseDecision, ...]

    @property
    def should_respond(self) -> bool:
        return any(d.should_respond for d in self.decisions)

    @property
    def responders(self) -> tuple[Persona, ...]:
        return tuple(d.persona for d in self.decisions if d.persona is not None)

    @property
    def reason(self) -> str:
        return self.decisions[0].reason

    @classmethod
    def silent(cls, reason: str) -> ResponsePlan:
        return cls((ResponseDecision(should_respond=False, persona=None, reason=reason),))


class Router:
    def __init__(self, *, default_persona: Persona = Persona.DOST) -> None:
        self._default = default_persona

    def route(self, turn: UserTurn, context: RoutingContext) -> ResponsePlan:
        text = turn.text
        named = self.named_personas(text)
        if named:
            return _plan(named, "named")

        if context.last_responder and context.bot_spoke_recently and is_follow_up(text):
            return _plan((context.last_responder,), "follow_up")

        if context.last_responder and context.bot_asked_question:
            if _names_a_human(text, context.other_humans):
                return ResponsePlan.silent("asked_another_human")
            return _plan((context.last_responder,), "answer")

        if is_question(text):
            if _names_a_human(text, context.other_humans):
                return ResponsePlan.silent("asked_another_human")
            bot = context.last_responder if context.bot_spoke_recently else None
            return _plan((bot or self._default,), "question")

        return ResponsePlan.silent("not_for_bots")

    @staticmethod
    def named_personas(text: str) -> tuple[Persona, ...]:
        """Bots named in the text, in the order they appear."""
        hits = [
            (match.start(), persona)
            for persona, pattern in _NAME_PATTERNS.items()
            if (match := pattern.search(text))
        ]
        return tuple(persona for _, persona in sorted(hits))


def is_follow_up(text: str) -> bool:
    return bool(_FOLLOW_UP.search(text))


def is_question(text: str) -> bool:
    return bool(_QUESTION.search(text))


_ENDS_WITH_QUESTION = re.compile(r"\?[\s\"'”’)]*$")


def asks_question(text: str) -> bool:
    """Does a bot reply end by asking the room something? ("... kya discuss karna hai?")"""
    return bool(_ENDS_WITH_QUESTION.search(text))


def _names_a_human(text: str, humans: frozenset[str]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(name.lower())}\b", lowered) for name in humans)


def _plan(personas: tuple[Persona, ...], reason: str) -> ResponsePlan:
    return ResponsePlan(
        tuple(ResponseDecision(should_respond=True, persona=p, reason=reason) for p in personas)
    )
