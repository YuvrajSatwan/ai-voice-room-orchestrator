"""Rooms: codes, validation, create/join rules, bots per room, and per-room memory."""

import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from fakes import make_brain

from roxstar.config import AGENT_NAME
from roxstar.domain import InputChannel
from roxstar.token_server import (
    NameTaken,
    RoomNotFound,
    clean_name,
    clean_title,
    create_room,
    new_room_code,
    normalize_room_code,
    prepare_join,
    room_slug,
    room_title,
)
from roxstar.worker import EmptyRoomWatch

# Codes and validation --------------------------------------------------------------------


def test_room_codes_are_readable_and_carry_the_title() -> None:
    code = new_room_code("Tech Talk!", choice=lambda alphabet: alphabet[0])
    assert code == "tech-talk-2222"
    assert normalize_room_code(code) == code


def test_titles_without_latin_letters_still_get_a_valid_code() -> None:
    assert room_slug("हिंदी बातचीत") == "room"
    assert room_slug("") == "room"
    assert room_slug("A very long room title that keeps going") == "a-very-long-room-tit"


@pytest.mark.parametrize(
    ("raw", "code"),
    [("tech-talk-8f3k", "tech-talk-8f3k"), ("  TECH-TALK-8F3K ", "tech-talk-8f3k"), ("abc", "abc")],
)
def test_room_codes_are_normalized(raw: str, code: str) -> None:
    assert normalize_room_code(raw) == code


@pytest.mark.parametrize(
    "raw", ["", "ab", "-abc", "abc-", "a--b", "../etc", "room/x", "a" * 49, "room_1", None]
)
def test_bad_room_codes_are_rejected(raw) -> None:
    with pytest.raises(ValueError):
        normalize_room_code(raw)


def test_names_are_trimmed_and_limited() -> None:
    assert clean_name("  Rahul   Sharma ") == "Rahul Sharma"
    assert clean_name("प्रिया") == "प्रिया"
    assert clean_name("Ri\x00ya​") == "Riya"  # control / invisible characters dropped
    with pytest.raises(ValueError):
        clean_name("   ")
    with pytest.raises(ValueError):
        clean_name("x" * 33)
    assert clean_title("") == ""


def test_room_title_comes_from_metadata() -> None:
    assert room_title(json.dumps({"title": "Tech Talk"})) == "Tech Talk"
    assert room_title("") == "" and room_title("not json") == "" and room_title("[1]") == ""


# Create / join against a fake LiveKit API ------------------------------------------------


class FakeLiveKit:
    """Just enough of LiveKitAPI: rooms, participants, dispatches."""

    def __init__(self) -> None:
        self.rooms: dict[str, SimpleNamespace] = {}
        self.people: dict[str, list[SimpleNamespace]] = {}
        self.dispatches: dict[str, list[SimpleNamespace]] = {}
        self.room = SimpleNamespace(
            list_rooms=self._list_rooms,
            create_room=self._create_room,
            list_participants=self._list_participants,
        )
        self.agent_dispatch = SimpleNamespace(
            list_dispatch=self._list_dispatch,
            create_dispatch=self._create_dispatch,
            delete_dispatch=self._delete_dispatch,
        )

    def add_person(self, room: str, identity: str, role: str = "") -> None:
        attributes = {"roxstar.role": role} if role else {}
        self.people.setdefault(room, []).append(
            SimpleNamespace(identity=identity, attributes=attributes)
        )

    async def _list_rooms(self, request):
        return SimpleNamespace(rooms=[self.rooms[n] for n in request.names if n in self.rooms])

    async def _create_room(self, request):
        self.rooms[request.name] = SimpleNamespace(name=request.name, metadata=request.metadata)

    async def _list_participants(self, request):
        return SimpleNamespace(participants=self.people.get(request.room, []))

    async def _list_dispatch(self, room):
        return self.dispatches.get(room, [])

    async def _create_dispatch(self, request):
        self.dispatches.setdefault(request.room, []).append(
            SimpleNamespace(
                id=f"d{len(self.dispatches)}",
                agent_name=request.agent_name,
                state=SimpleNamespace(created_at=time.time_ns()),
            )
        )

    async def _delete_dispatch(self, dispatch_id, room):
        self.dispatches[room] = [d for d in self.dispatches[room] if d.id != dispatch_id]


async def test_created_room_is_a_real_livekit_room_with_its_title() -> None:
    lk = FakeLiveKit()
    code = await create_room(lk, "Tech Talk")
    assert code.startswith("tech-talk-") and code in lk.rooms
    assert room_title(lk.rooms[code].metadata) == "Tech Talk"
    assert lk.dispatches == {}  # bots are sent in when someone actually enters


async def test_joining_brings_the_bots_into_that_room_only() -> None:
    lk = FakeLiveKit()
    room_a = await create_room(lk, "A")
    room_b = await create_room(lk, "B")
    assert await prepare_join(lk, room=room_a, name="Rahul", mode="join") == "A"
    assert [d.agent_name for d in lk.dispatches[room_a]] == [AGENT_NAME]
    assert room_b not in lk.dispatches


async def test_joining_a_room_that_does_not_exist_fails() -> None:
    lk = FakeLiveKit()
    with pytest.raises(RoomNotFound):
        await prepare_join(lk, room="nope-1234", name="Rahul", mode="join")
    with pytest.raises(RoomNotFound):
        await prepare_join(lk, room="nope-1234", name="Rahul", mode="rejoin")
    assert lk.rooms == {} and lk.dispatches == {}


async def test_a_name_already_in_the_room_is_refused_but_rejoin_is_allowed() -> None:
    lk = FakeLiveKit()
    room = await create_room(lk, "")
    lk.add_person(room, "Rahul")
    with pytest.raises(NameTaken):
        await prepare_join(lk, room=room, name="rahul", mode="join")
    await prepare_join(lk, room=room, name="Rahul", mode="rejoin")
    await prepare_join(lk, room=room, name="Priya", mode="join")


async def test_second_person_does_not_dispatch_a_second_brain() -> None:
    lk = FakeLiveKit()
    room = await create_room(lk, "")
    await prepare_join(lk, room=room, name="Rahul", mode="join")
    lk.add_person(room, "brain-1", role="brain")
    await prepare_join(lk, room=room, name="Priya", mode="join")
    assert len(lk.dispatches[room]) == 1


async def test_old_clients_without_a_mode_still_get_a_room() -> None:
    lk = FakeLiveKit()
    await prepare_join(lk, room="roxstar-qa", name="Rahul", mode=None)
    assert "roxstar-qa" in lk.rooms and lk.dispatches["roxstar-qa"]


# The worker leaves an empty room ---------------------------------------------------------


async def test_worker_leaves_after_the_last_human_is_gone_for_the_grace_period() -> None:
    humans = {"Rahul"}
    closed: list[bool] = []
    watch = EmptyRoomWatch(lambda: bool(humans), lambda: closed.append(True), grace_s=0.05)
    watch.check()
    humans.clear()
    watch.check()
    await asyncio.sleep(0.1)
    assert closed == [True]


async def test_a_human_returning_during_the_grace_period_keeps_the_room() -> None:
    humans: set[str] = set()
    closed: list[bool] = []
    watch = EmptyRoomWatch(lambda: bool(humans), lambda: closed.append(True), grace_s=0.05)
    watch.check()  # job started, nobody connected yet
    humans.add("Rahul")
    watch.check()
    await asyncio.sleep(0.1)
    assert closed == []


# Each room has its own memory ------------------------------------------------------------


async def test_two_rooms_never_share_conversation_memory() -> None:
    room_a, _, _, llm_a = make_brain()
    room_b, _, _, llm_b = make_brain()
    await room_a.handle_turn(
        speaker="Rahul", text="Mera naam Rahul hai aur mujhe cricket pasand hai.",
        channel=InputChannel.TEXT,
    )  # fmt: skip
    await room_b.handle_turn(
        speaker="Rahul", text="Maine apne baare mein kya bataya tha?", channel=InputChannel.VOICE
    )
    assert "cricket" not in llm_b.last_prompt()
    assert room_b.memory.facts_for("Rahul") == ()
    assert room_a.memory.facts_for("Rahul")
