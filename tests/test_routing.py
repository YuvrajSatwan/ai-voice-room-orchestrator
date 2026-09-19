import pytest

from roxstar.domain import InputChannel, Persona
from roxstar.domain import UserTurn as Turn
from roxstar.routing import Router, RoutingContext

router = Router()
DOST, SATHI = Persona.DOST, Persona.SATHI


def route(
    text: str,
    last: Persona | None = None,
    recent: bool = True,
    humans: frozenset[str] = frozenset({"Priya"}),
):
    turn = Turn.now(room_name="r", speaker_id="Rahul", text=text, channel=InputChannel.VOICE)
    context = RoutingContext(last_responder=last, bot_spoke_recently=recent, other_humans=humans)
    return router.route(turn, context)


# 1. Named ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("AI Dost, AI kya hota hai?", DOST),
        ("Sathi, can you explain cloud computing?", SATHI),
        ("Saathi ek example do", SATHI),
        ("AI दोस्त, cloud क्या है?", DOST),  # STT codemix output
        ("Hello AI साथी।", SATHI),  # heard in the live test
    ],
)
def test_a_named_bot_always_answers(text: str, expected: Persona) -> None:
    other = SATHI if expected is DOST else DOST
    plan = route(text, last=other)
    assert plan.responders == (expected,) and plan.reason == "named"


def test_both_bots_named_answer_in_the_order_named() -> None:
    assert route("AI Dost, tum answer karo. AI Sathi, baad mein ek example dena.").responders == (
        DOST,
        SATHI,
    )
    assert route("Sathi pehle bolo, phir Dost").responders == (SATHI, DOST)


# 2. Follow-up -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Unki koi famous movie batao",
        "Thoda aur simple batao",
        "wahi topic continue karo",
        "उसकी movie बताओ",
        "यह बहुत ज्यादा लंबा है, थोड़ा छोटा करो",  # heard in the live test
        "phir se bolo",
        "Another one.",  # missed in a live test
        "ek aur sunao",
    ],
)
def test_follow_up_goes_to_the_bot_that_spoke_last(text: str) -> None:
    plan = route(text, last=SATHI)
    assert plan.responders == (SATHI,) and plan.reason == "follow_up"


def test_follow_up_long_after_the_bot_spoke_is_not_a_follow_up() -> None:
    assert not route("thoda aur simple", last=SATHI, recent=False).should_respond


# 3. Questions -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "AI kya hota hai?",
        "Can you explain cloud computing?",
        "Shah Rukh Khan ke baare mein batao",
        "मुझे 1 बात बताओ simple भाषा में AI क्या है",  # heard in the live test
        "Maine apne baare mein kya bataya tha?",
        "यार मुझे English में coffee के ऊपर एक joke सुनाओ",  # missed in a live test
        "koi achha sa gaana sunao",
    ],
)
def test_unnamed_questions_are_answered(text: str) -> None:
    plan = route(text, last=None, recent=False)
    assert plan.responders == (DOST,) and plan.reason == "question"


def test_a_question_mid_conversation_stays_with_the_current_bot() -> None:
    assert route("Aur cloud kya hai?", last=SATHI).responders == (SATHI,)


def test_a_question_to_another_human_is_left_alone() -> None:
    plan = route("Priya, tum kal kya kar rahi ho?")
    assert not plan.should_respond and plan.reason == "asked_another_human"


# 4. Silence -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "ohh",
        "ok",
        "नहीं यार thank you बताने के लिए।",  # heard in the live test, got a reply before
        "ओह तो ऐसा है।",
        "Mera naam Rahul hai aur mujhe cricket pasand hai.",
        "haan main bhi yahi soch raha tha",
        "मेरी आवाज आ रही है।",  # mic check from the live test: correctly ignored
        "It's working.",
    ],
)
def test_chatter_and_statements_get_no_reply(text: str) -> None:
    plan = route(text, last=DOST)
    assert not plan.should_respond and plan.reason == "not_for_bots"
