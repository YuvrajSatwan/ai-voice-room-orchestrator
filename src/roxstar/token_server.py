"""The room service: creates rooms and issues short-lived LiveKit tokens.

    POST /rooms  {title?}             -> {room, title}   a new LiveKit room with a fresh code
    POST /token  {name, room, mode?}  -> {token, url, room, title}
                                         and makes sure Kabir + Saraah are in that room

Every room is a real LiveKit room named by its code (e.g. "tech-talk-8f3k"). The worker is
dispatched per room, so each room gets its own brain, bots and memory. Only a signed
participant token and the public LiveKit URL leave this server; credentials stay here.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
import unicodedata
from collections.abc import Awaitable, Callable
from datetime import timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any

from livekit import api

from roxstar.config import AGENT_NAME, ConfigurationError, Settings
from roxstar.names import addressed_bots

_dispatch_lock = Lock()
_JOIN_GRACE_S = 30.0
# A created room waits this long for its first person; then LiveKit closes it.
_NEW_ROOM_TIMEOUT_S = 600

NAME_MAX = 32
TITLE_MAX = 40
_ROOM_CODE = re.compile(r"^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$")  # 3-48 characters
_CODE_SUFFIX_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"  # no 0/o or 1/l/i mix-ups


class RoomServiceError(Exception):
    """A request that can't be served, with the HTTP status the browser should see."""

    status = HTTPStatus.BAD_REQUEST


class RoomNotFound(RoomServiceError):
    status = HTTPStatus.NOT_FOUND


class NameTaken(RoomServiceError):
    status = HTTPStatus.CONFLICT


def normalize_room_code(raw: object) -> str:
    """'  Tech-Talk-8F3K ' -> 'tech-talk-8f3k'. Raises ValueError if it can't be a room code."""
    code = re.sub(r"\s+", "-", str(raw or "").strip().lower())
    if not _ROOM_CODE.match(code) or "--" in code:
        raise ValueError("Room codes are 3-48 letters, numbers and dashes, like tech-talk-8f3k")
    return code


def _clean_text(raw: object, *, limit: int) -> str:
    """Drop control/format characters and collapse spaces. Hindi and other scripts are kept."""
    text = "".join(ch for ch in str(raw or "") if unicodedata.category(ch)[0] != "C")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        raise ValueError(f"Keep it under {limit} characters")
    return text


def clean_name(raw: object) -> str:
    """A display name: 1-32 visible characters. It is also the participant identity."""
    name = _clean_text(raw, limit=NAME_MAX)
    if not name:
        raise ValueError("Please enter your name")
    if addressed_bots(name):
        # A human called "Kabir" or "Sara" would make every mention of that name ambiguous.
        raise ValueError("Kabir and Saraah are the AI participants' names. Please pick another.")
    return name


def clean_title(raw: object) -> str:
    return _clean_text(raw, limit=TITLE_MAX)


def room_slug(title: str) -> str:
    """'Tech Talk!' -> 'tech-talk'. Titles with no Latin letters fall back to 'room'."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:20].strip("-")
    return slug or "room"


def new_room_code(title: str, *, choice: Callable[[str], str] = secrets.choice) -> str:
    """'Tech Talk' -> 'tech-talk-8f3k': easy to read out, hard to guess."""
    suffix = "".join(choice(_CODE_SUFFIX_ALPHABET) for _ in range(4))
    return f"{room_slug(title)}-{suffix}"


def room_title(metadata: str) -> str:
    """The title stored in a room's metadata by ``create_room``, or ''."""
    try:
        title = json.loads(metadata or "{}").get("title", "")
    except (ValueError, AttributeError):
        return ""
    return title if isinstance(title, str) else ""


def create_token(settings: Settings, *, identity: str, room: str) -> str:
    """Create a room-scoped token for one browser participant."""
    return (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_ttl(timedelta(hours=1))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )


def dispatch_action(
    *, brain_present: bool, dispatch_ages_s: list[float], grace_s: float = _JOIN_GRACE_S
) -> str:
    """Decide whether this room needs the worker sent in: 'keep', 'create' or 'replace'.

    A dispatch record can outlive its worker (e.g. the worker restarted while people stayed
    in the room), so "a dispatch exists" is not proof the bots are there. The brain actually
    being in the room is. A dispatch younger than ``grace_s`` is left alone: its brain is
    probably still joining, and a second dispatch would put two brains in one room.
    """
    if brain_present or any(age < grace_s for age in dispatch_ages_s):
        return "keep"
    return "replace" if dispatch_ages_s else "create"


async def create_room(livekit_api: Any, title: str) -> str:
    """Create a new, empty LiveKit room with a fresh code. The title rides in room metadata."""
    for _ in range(5):
        code = new_room_code(title)
        existing = await livekit_api.room.list_rooms(api.ListRoomsRequest(names=[code]))
        if not existing.rooms:
            await livekit_api.room.create_room(
                api.CreateRoomRequest(
                    name=code,
                    empty_timeout=_NEW_ROOM_TIMEOUT_S,
                    metadata=json.dumps({"title": title}),
                )
            )
            return code
    raise RuntimeError("Could not find a free room code")


async def prepare_join(livekit_api: Any, *, room: str, name: str, mode: str | None) -> str:
    """Check the room before handing out a token, and bring the bots in. Returns its title.

    mode "join":   the room must exist (made by POST /rooms), and the name must be free in
                   it: the name is the participant identity, and LiveKit would silently kick
                   the earlier person with the same identity.
    mode "rejoin": the same person coming back after a dropped connection. Their old
                   participant may still be listed for a few seconds, so no name check.
    no mode:       older clients; the room is created if it doesn't exist.
    """
    rooms = await livekit_api.room.list_rooms(api.ListRoomsRequest(names=[room]))
    participants: list[Any] = []
    title = ""
    if rooms.rooms:
        title = room_title(rooms.rooms[0].metadata)
        listing = await livekit_api.room.list_participants(api.ListParticipantsRequest(room=room))
        participants = list(listing.participants)
        if mode == "join" and any(p.identity.casefold() == name.casefold() for p in participants):
            raise NameTaken(f"Someone called {name} is already in this room. Try another name.")
    elif mode in ("join", "rejoin"):
        raise RoomNotFound("This room doesn't exist or has ended. Check the code, or create one.")
    else:
        await livekit_api.room.create_room(api.CreateRoomRequest(name=room, empty_timeout=300))

    ours = [
        d for d in await livekit_api.agent_dispatch.list_dispatch(room)
        if d.agent_name == AGENT_NAME
    ]  # fmt: skip
    now = time.time()
    action = dispatch_action(
        brain_present=any(p.attributes.get("roxstar.role") == "brain" for p in participants),
        dispatch_ages_s=[now - d.state.created_at / 1e9 for d in ours],
    )
    if action != "keep":
        for stale in ours:  # "replace": the worker that owned these is gone
            await livekit_api.agent_dispatch.delete_dispatch(stale.id, room)
        await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room)
        )
    return title


def _with_livekit(settings: Settings, work: Callable[[Any], Awaitable[Any]]) -> Any:
    """Run one LiveKit API conversation from the threaded HTTP handler, one at a time.

    The lock also stops two browsers joining at once from dispatching two brains.
    """

    async def run() -> Any:
        async with api.LiveKitAPI(
            url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        ) as livekit_api:
            return await work(livekit_api)

    with _dispatch_lock:
        return asyncio.run(run())


class TokenHandler(BaseHTTPRequestHandler):
    """Minimal CORS-enabled JSON handler for the web UI."""

    settings: Settings

    def _send_json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        origin = self.headers.get("Origin", "*")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/health"):
            self._send_json(HTTPStatus.OK, {"status": "ok", "service": "roxstar-token-server"})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > 8_192:
            raise ValueError("Request is too large")
        body = json.loads(self.rfile.read(content_length) or b"{}")
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object")
        return body

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in ("/token", "/rooms"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        try:
            body = self._read_json()
            if self.path == "/rooms":
                title = clean_title(body.get("title"))
                room = _with_livekit(self.settings, lambda lk: create_room(lk, title))
                self._send_json(HTTPStatus.CREATED, {"room": room, "title": title})
                return

            name = clean_name(body.get("name"))
            room = normalize_room_code(body.get("room"))
            mode = body.get("mode")
            if mode not in (None, "join", "rejoin"):
                raise ValueError("Unknown mode")
            title = _with_livekit(
                self.settings, lambda lk: prepare_join(lk, room=room, name=name, mode=mode)
            )
            self._send_json(
                HTTPStatus.OK,
                {
                    "token": create_token(self.settings, identity=name, room=room),
                    "url": self.settings.livekit_url,
                    "room": room,
                    "title": title,
                },
            )
        except RoomServiceError as exc:
            self._send_json(exc.status, {"error": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unable to start session"})

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep the HTTP helper quiet; the worker owns structured logs."""


def main() -> None:
    """Start the room service on http://HOST:PORT (defaults 0.0.0.0:8000)."""
    try:
        settings = Settings.from_environment(require_livekit=True)
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from exc
    TokenHandler.settings = settings
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    ThreadingHTTPServer((host, port), TokenHandler).serve_forever()


if __name__ == "__main__":
    main()
