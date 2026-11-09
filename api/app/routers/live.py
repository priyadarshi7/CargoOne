"""The WebSocket the screens listen on. Sign-in is the first message (never the address, which ends up in logs):
{"auth": "Bearer <token>"} for a signed-in person or {"auth": "Link <token>"} for a hired driver's private link."""
import asyncio
import uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.config import get_settings
from app.db import SessionLocal
from app.live import Conn, hub
from app.models import AccessLink, LinkKind, Role, Trip, User
from app.security import link_hash

router = APIRouter(tags=["live"])
AUTH_WAIT_S = 10
PING_S = 25


async def authenticate(raw: str) -> Conn | None:
    scheme, _, token = (raw or "").partition(" ")
    scheme, token = scheme.lower(), token.strip()
    async with SessionLocal() as session:
        if scheme == "link" and 20 <= len(token) <= 128:
            link = await session.get(AccessLink, link_hash(token))
            if link is None or link.kind != LinkKind.sms_upload or link.revoked or link.expires_at <= datetime.now(UTC):
                return None
            trip = await session.get(Trip, link.trip_id)
            user = await session.get(User, trip.driver_id) if trip is not None and trip.driver_id else None
            if user is not None and user.role != Role.driver:
                return None
        elif scheme == "bearer":
            try:
                claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
                user = await session.get(User, uuid.UUID(claims["sub"]))
            except (jwt.PyJWTError, ValueError, KeyError):
                return None
            if user is not None and claims.get("ver", 0) != user.token_version:
                return None  # signed in before the password or PIN was changed
        else:
            return None
        if user is None or not user.is_active:
            return None
        return Conn(user_id=user.id, role=user.role, client_id=user.client_id)


@router.websocket("/ws")
async def live(ws: WebSocket) -> None:
    await ws.accept()
    conn: Conn | None = None
    try:
        first = await asyncio.wait_for(ws.receive_json(), AUTH_WAIT_S)
        conn = await authenticate(str(first.get("auth", ""))) if isinstance(first, dict) else None
    except (TimeoutError, WebSocketDisconnect, ValueError, RuntimeError):
        conn = None
    if conn is None or not hub.add(conn):
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.close(code=4401 if conn is None else 4429)
        return
    await ws.send_json({"t": "ready"})

    async def send() -> None:
        while True:
            try:
                msg = await asyncio.wait_for(conn.queue.get(), PING_S)
            except TimeoutError:
                msg = {"t": "ping"}  # keeps proxies from closing a quiet connection
            await ws.send_json(msg)

    async def listen() -> None:
        while True:
            await ws.receive_text()  # nothing is expected from the screen; this is how a closed one is noticed

    tasks = [asyncio.create_task(send()), asyncio.create_task(listen())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        hub.remove(conn)
