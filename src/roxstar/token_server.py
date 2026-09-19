"""Small development-only HTTP endpoint that issues short-lived LiveKit tokens.

Run this locally next to the worker.  It deliberately returns only a signed
participant token and the public LiveKit URL; provider credentials stay here.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any

from livekit import api

from roxstar.config import AGENT_NAME, ConfigurationError, Settings

_dispatch_lock = Lock()
_JOIN_GRACE_S = 30.0


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


async def _ensure_agent_dispatch(settings: Settings, room: str) -> None:
    """Make sure the Roxstar worker (which brings both bots) is in this room."""
    async with api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    ) as livekit_api:
        rooms = await livekit_api.room.list_rooms(api.ListRoomsRequest(names=[room]))
        participants = []
        if rooms.rooms:
            listing = await livekit_api.room.list_participants(
                api.ListParticipantsRequest(room=room)
            )
            participants = listing.participants
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
        if action == "keep":
            return
        for stale in ours:  # "replace": the worker that owned these is gone
            await livekit_api.agent_dispatch.delete_dispatch(stale.id, room)
        await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room)
        )


def ensure_agent_dispatch(settings: Settings, room: str) -> None:
    """Synchronously dispatch for the stdlib HTTP handler without duplicate jobs."""
    with _dispatch_lock:
        asyncio.run(_ensure_agent_dispatch(settings, room))


class TokenHandler(BaseHTTPRequestHandler):
    """Minimal CORS-enabled handler for the local Vite development server."""

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
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/token":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > 8_192:
                raise ValueError("Request is too large")
            body = json.loads(self.rfile.read(content_length) or b"{}")
            name = str(body.get("name", "")).strip()
            room = str(body.get("room", "")).strip()
            if not name or not room:
                raise ValueError("Name and room are required")
            if len(name) > 64 or len(room) > 128:
                raise ValueError("Name or room is too long")
            ensure_agent_dispatch(self.settings, room)
            self._send_json(
                HTTPStatus.OK,
                {
                    "token": create_token(self.settings, identity=name, room=room),
                    "url": self.settings.livekit_url,
                },
            )
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unable to start session"})

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep the development helper quiet; the worker owns structured logs."""


def main() -> None:
    """Start the token service on http://host:port."""
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
