"""Live updates: when something changes in the database, every open screen that could show it is told to look again.

The message carries only a topic name ("trips", "review", ...), never data, so nothing can leak through it: the screen asks the API
for the fresh data with its own sign-in, as it always did. A change is noticed in one place, when a database transaction commits
(see `_collect`), so no endpoint has to remember to announce anything.

Single process by design (the connections live in this process's memory). With several API instances, publish through Redis or
Postgres LISTEN/NOTIFY instead (see docs/03-decisions.md)."""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import event
from sqlalchemy.orm import Session as SyncSession

from app import models as m

log = logging.getLogger("cargoone.live")
OFFICE = {m.Role.ops, m.Role.billing, m.Role.md, m.Role.admin}
MAX_PER_USER = 5
QUEUE = 20


@dataclass(eq=False)
class Conn:
    user_id: uuid.UUID
    role: m.Role
    client_id: uuid.UUID | None = None
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(QUEUE))


# What changed -> which topic. LocationPing is left out on purpose: it changes every few seconds and the map has its own refresh.
TOPICS: dict[type, tuple[str, ...]] = {
    m.Trip: ("trips", "review"), m.PodSubmission: ("trips", "review"), m.TripEvent: ("trips",),
    m.Invoice: ("billing", "trips"), m.Payment: ("billing", "trips"), m.OnlinePayment: ("billing",),
    m.TransportRequest: ("requests",), m.Expense: ("expenses",), m.Advance: ("expenses",),
    m.Notification: ("messages",), m.PrivacyRequest: ("privacy",),
    m.User: ("setup",), m.Vehicle: ("setup",), m.Client: ("setup",), m.Branch: ("setup",),
}
Change = tuple[str, uuid.UUID | None, uuid.UUID | None]  # (topic, the client it concerns, the person it concerns)


def changes_of(obj: object) -> set[Change]:
    topics = TOPICS.get(type(obj))
    if not topics:
        return set()
    client = getattr(obj, "client_id", None) or (obj.id if isinstance(obj, m.Client) else None)
    who = getattr(obj, "driver_id", None) or getattr(obj, "user_id", None) or (obj.id if isinstance(obj, m.User) else None)
    return {(t, client, who) for t in topics}


class Hub:
    def __init__(self) -> None:
        self.conns: set[Conn] = set()

    def add(self, conn: Conn) -> bool:
        if sum(c.user_id == conn.user_id for c in self.conns) >= MAX_PER_USER:
            return False
        self.conns.add(conn)
        return True

    def remove(self, conn: Conn) -> None:
        self.conns.discard(conn)

    @staticmethod
    def _wants(conn: Conn, ch: Change) -> bool:
        topic, client, who = ch
        if conn.role in OFFICE:
            return topic != "messages"  # a person's own inbox is theirs, not the office's
        if conn.role == m.Role.driver:
            return topic in ("trips", "expenses", "messages") and who == conn.user_id
        if conn.role == m.Role.client:
            return topic in ("trips", "billing", "requests") and client is not None and client == conn.client_id
        return False

    def publish(self, changes: set[Change]) -> None:
        """Never waits and never fails: a slow or gone screen must not hold up the request that changed the data."""
        for conn in list(self.conns):
            topics = sorted({t for t, c, w in changes if self._wants(conn, (t, c, w))})
            if not topics:
                continue
            try:
                conn.queue.put_nowait({"t": "change", "topics": topics})
            except asyncio.QueueFull:  # it has fallen behind: one catch-up message instead of the missed ones
                while not conn.queue.empty():
                    conn.queue.get_nowait()
                conn.queue.put_nowait({"t": "change", "topics": ["*"]})


hub = Hub()


@event.listens_for(SyncSession, "after_flush")
def _collect(session: SyncSession, _ctx: object) -> None:
    if not hub.conns:
        return
    seen: set[Change] = session.info.setdefault("live", set())
    for obj in (*session.new, *session.dirty, *session.deleted):
        seen |= changes_of(obj)


@event.listens_for(SyncSession, "after_commit")
def _announce(session: SyncSession) -> None:
    seen = session.info.pop("live", None)
    if seen:
        try:
            hub.publish(seen)
        except Exception:  # announcing is a courtesy; the commit already happened
            log.exception("live publish failed")


@event.listens_for(SyncSession, "after_rollback")
def _forget(session: SyncSession) -> None:
    session.info.pop("live", None)
