"""Web Push: an alert that reaches a driver's phone even when the app is closed.

The phone gives the browser's push service permission to wake our service worker; we store that address (a PushSubscription) and
send a small signed message to it. Two behaviours, like WhatsApp and email:

* live, when both VAPID keys are set: the message really goes out (pywebpush, in a thread so the request is never blocked);
* recording, when they are not: nothing is sent and the screen says so.

Sending never blocks or breaks the action that caused it: it runs in the background, failures are logged, and a phone whose
subscription the push service says is gone (404 or 410) is forgotten."""
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SessionLocal
from app.models import PushSubscription

log = logging.getLogger("cargoone.push")


@dataclass(frozen=True)
class Target:
    id: uuid.UUID
    endpoint: str
    p256dh: str
    auth: str


def live() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


# Messages sent in recording mode (tests and local inspection): (user_id, payload)
outbox: list[tuple[uuid.UUID, dict]] = []
_tasks: set[asyncio.Task] = set()


def _send_one(target: Target, payload: str) -> int:
    """Blocking: send one push. Returns the HTTP status the push service answered (201 means accepted). Overridden in tests."""
    from pywebpush import WebPushException, webpush  # imported here: only live mode needs it

    s = get_settings()
    try:
        res = webpush(
            subscription_info={"endpoint": target.endpoint, "keys": {"p256dh": target.p256dh, "auth": target.auth}},
            data=payload, vapid_private_key=s.vapid_private_key, vapid_claims={"sub": s.vapid_subject}, ttl=3600 * 12, timeout=10,
        )
        return res.status_code
    except WebPushException as e:
        return e.response.status_code if e.response is not None else 0


async def _deliver(targets: list[Target], payload: str) -> None:
    gone: list[uuid.UUID] = []
    ok: list[uuid.UUID] = []
    for t in targets:
        try:
            code = await asyncio.to_thread(_send_one, t, payload)
        except Exception:
            log.exception("push sender crashed")
            continue
        if code in (404, 410):
            gone.append(t.id)
        elif 200 <= code < 300:
            ok.append(t.id)
        else:
            log.warning("push not accepted: status %s", code)
    if gone or ok:
        async with SessionLocal() as s:
            if gone:
                await s.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
            if ok:
                await s.execute(update(PushSubscription).where(PushSubscription.id.in_(ok)).values(last_ok_at=func.now()))
            await s.commit()


async def push_user(session: AsyncSession, user_id: uuid.UUID, title: str, body: str, link: str | None = None, *, wait: bool = False) -> int:
    """Alert every phone this person has allowed. Returns how many phones were addressed (0 when none, or when only recording)."""
    rows = (await session.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))).scalars().all()
    payload = {"title": title[:80], "body": body[:200], "url": link or "/driver"}
    if not live():
        outbox.append((user_id, payload))
        return 0
    if not rows:
        return 0
    targets = [Target(r.id, r.endpoint, r.p256dh, r.auth) for r in rows]
    work = asyncio.create_task(_deliver(targets, json.dumps(payload)))
    if wait:
        await work
    else:
        _tasks.add(work)
        work.add_done_callback(_tasks.discard)
    return len(targets)


async def drain() -> None:
    """Wait for background sends to finish (tests, shutdown)."""
    if _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
