"""Server-sent events over PostgreSQL LISTEN/NOTIFY.

`broadcast()` stores an event and sends its id and topic with NOTIFY. Every web process listens on
CHANNEL, loads the events its open streams subscribe to and writes them to those streams. The
stored events answer `Last-Event-ID` after a reconnect.
"""

import asyncio
import contextlib
import logging
import re
import weakref
from dataclasses import dataclass
from functools import partial
from importlib import import_module
from typing import Any

import psycopg
from asgiref.sync import sync_to_async
from django.db import connection, transaction
from django.db.models import Max
from django.http import HttpResponseBadRequest, HttpResponseForbidden, StreamingHttpResponse
from django.http.response import HttpResponseBase
from psycopg import sql

# A string, so the template repository stays valid Python before startproject renders it.
StreamEvent = import_module("{{ project_name }}.models").StreamEvent

logger = logging.getLogger(__name__)

CHANNEL = "sse"
# close_streams() stores its targets as events on this topic, so they replay like any event.
# can_subscribe() refuses it, since its kind is neither "public" nor "user".
CLOSE_TOPIC = "_close"
KEEPALIVE_SECONDS = 15
QUEUE_SIZE = 1000
# A longer replay ends the stream after one batch; htmx reconnects and asks for the next.
REPLAY_BATCH = 500
RECONNECT_DELAYS = (0.5, 1, 2, 5)

# Serialises event writers, so ids become visible in the order they are assigned.
# Replay after Last-Event-ID would skip an event whose smaller id committed late.
PUBLISH_LOCK_KEY = int.from_bytes(b"sse-emit", signed=True)


def broadcast(topic: str, html: str, event: str = "") -> None:
    """Send `html` to every stream subscribed to `topic`, once the current transaction commits.

    A rollback sends nothing. With a name in `event`, htmx dispatches a DOM event instead of
    swapping the html.
    """
    if _LINE_BREAK.search(event):
        raise ValueError("An SSE event name cannot contain a line break.")
    # robust: the caller's transaction has committed, so a failure here is logged, not raised.
    transaction.on_commit(partial(_publish, topic, html, event), robust=True)


def _publish(topic: str, html: str, event: str) -> None:
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [PUBLISH_LOCK_KEY])
        stored = StreamEvent.objects.create(topic=topic, event=event, html=html)
        _notify(cursor, stored.id, topic)


def close_streams(*, user=None, session=None) -> None:
    """End the open streams of `user` or of one session, once the current transaction commits.

    Each stream receives an event named "closed" and ends. htmx reconnects, and can_subscribe()
    checks the topics again, so call this after taking away a user's access to a topic.
    """
    if user is None and session is None:
        raise ValueError("close_streams() needs a user or a session.")
    # A session without a key was never saved, so no stream was opened with it.
    targets = Owner.of(
        user=str(user.pk) if user is not None else None,
        session=session.session_key if session is not None else None,
    ).targets
    for target in sorted(targets):
        broadcast(CLOSE_TOPIC, target)


def close_session_streams(sender, request, user, **kwargs) -> None:
    """A user_logged_out receiver: other tabs of the session lose the user's topics."""
    if request is not None:
        close_streams(session=request.session)


def _notify(cursor, event_id: int, topic: str) -> None:
    # NOTIFY payloads are limited to 8000 bytes, so the html stays in the table.
    # The topic lets a process without subscribers skip loading the event.
    cursor.execute("SELECT pg_notify(%s, %s)", [CHANNEL, f"{event_id}:{topic}"])


def parse_payload(payload: str) -> tuple[int, str] | None:
    """The id and topic of a NOTIFY from `_notify()`, or None for any other payload."""
    event_id, _, topic = payload.partition(":")
    if not (event_id.isascii() and event_id.isdigit()):
        return None
    return int(event_id), topic


def parse_last_event_id(value: str) -> int | None:
    # isdigit() alone accepts characters such as "²", which int() rejects.
    return int(value) if value.isascii() and value.isdigit() else None


# SSE ends a line at CRLF, CR or LF, so each of them must start a new data field.
_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def format_event(event) -> str:
    """The event as an SSE message. Each line of the html gets its own data field."""
    lines = [f"id: {event.id}"]
    if event.event:
        lines.append(f"event: {event.event}")
    lines += [f"data: {line}" for line in _LINE_BREAK.split(event.html)]
    return "\n".join(lines) + "\n\n"


def can_subscribe(request, topic: str) -> bool:
    """Decides whether the requesting user may receive the events of `topic`.

    Extend it for the project's own topics, such as chat rooms. Unknown kinds stay closed.
    """
    kind, _, key = topic.partition(":")
    match kind:
        case "public":
            return True
        case "user":
            return request.user.is_authenticated and key == str(request.user.pk)
        case _:
            return False


@dataclass(frozen=True)
class Message:
    id: int
    topic: str
    event: str
    html: str


# Put into a stream's queue when its client falls too far behind. The stream ends, and htmx
# reconnects with Last-Event-ID, so the replay delivers what the queue dropped.
OVERFLOW = object()
# Put into a stream's queue by Hub._close(). The stream sends CLOSED and ends.
REVOKED = object()
CLOSED = "event: closed\ndata: \n\n"


@dataclass(frozen=True)
class Owner:
    """The targets close_streams() matches against a stream."""

    targets: frozenset[str]

    @classmethod
    def of(cls, *, user: str | None, session: str | None) -> Owner:
        targets = set()
        if user is not None:
            targets.add(f"user:{user}")
        if session is not None:
            targets.add(f"session:{session}")
        return cls(frozenset(targets))


def connect_params() -> dict[str, Any]:
    """Arguments for a psycopg connection to the default database, outside Django's pool."""
    # The stub declares None, the return type of the base class's abstract method.
    params: dict[str, Any] = connection.get_connection_params()  # pyright: ignore[reportAssignmentType]
    # Django's sync cursor factory and adapter context do not fit an AsyncConnection.
    params.pop("cursor_factory", None)
    params.pop("context", None)
    return params


class Hub:
    """Fans NOTIFY out to the open streams of one event loop, which is one granian worker.

    It holds two connections of its own, outside Django's pool: one waits on LISTEN, the other
    loads events. An open stream therefore holds no pooled connection.
    """

    def __init__(self) -> None:
        self.queues: dict[str, set[asyncio.Queue]] = {}
        self.by_target: dict[str, set[asyncio.Queue]] = {}
        # Closed streams get no further events, so nothing can push their REVOKED out.
        self.revoked: set[asyncio.Queue] = set()
        self.ready = asyncio.Event()
        self.last_id: int | None = None
        self.task: asyncio.Task | None = None
        self.fetch_connection: psycopg.AsyncConnection | None = None
        self.fetch_lock = asyncio.Lock()

    def subscribe(self, topics: list[str], owner: Owner) -> asyncio.Queue:
        """A queue that receives the events of `topics`. Starts the listener on first use."""
        queue: asyncio.Queue = asyncio.Queue(QUEUE_SIZE)
        for target in owner.targets:
            self.by_target.setdefault(target, set()).add(queue)
        for topic in topics:
            self.queues.setdefault(topic, set()).add(queue)
        if self.task is None or self.task.done():
            self.task = asyncio.get_running_loop().create_task(self._listen())
        return queue

    def unsubscribe(self, topics: list[str], owner: Owner, queue: asyncio.Queue) -> None:
        self.revoked.discard(queue)
        _discard(self.by_target, owner.targets, queue)
        _discard(self.queues, topics, queue)

    async def replay(self, topics: list[str], after_id: int) -> list[Message]:
        """Up to REPLAY_BATCH events of `topics` after `after_id`, oldest first."""
        query = _select("WHERE topic = ANY(%s) AND id > %s ORDER BY id LIMIT %s")
        rows = await self._fetch(query, [topics, after_id, REPLAY_BATCH])
        return [Message(*row) for row in rows]

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        if self.fetch_connection is not None:
            await self.fetch_connection.close()

    async def _fetch(self, query: sql.Composed, params: list[Any]) -> list[tuple]:
        async with self.fetch_lock:
            if self.fetch_connection is None or self.fetch_connection.broken:
                self.fetch_connection = await psycopg.AsyncConnection.connect(
                    **connect_params(), autocommit=True
                )
            cursor = await self.fetch_connection.execute(query, params)
            return await cursor.fetchall()

    async def _listen(self) -> None:
        delays = RECONNECT_DELAYS
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    **connect_params(), autocommit=True
                ) as listening:
                    await listening.execute(sql.SQL("LISTEN {}").format(sql.Identifier(CHANNEL)))
                    await self._catch_up()
                    self.ready.set()
                    delays = RECONNECT_DELAYS
                    async for notify in listening.notifies():
                        await self._receive(notify.payload)
            except psycopg.Error:
                logger.warning("The SSE listener lost its connection; reconnecting.", exc_info=True)
            self.ready.clear()
            await asyncio.sleep(delays[0])
            delays = delays[1:] or delays

    async def _receive(self, payload: str) -> None:
        parsed = parse_payload(payload)
        if parsed is None:
            logger.warning("Ignored a NOTIFY on %s with the payload %r.", CHANNEL, payload)
            return
        event_id, topic = parsed
        readers = self.by_target if topic == CLOSE_TOPIC else self.queues.get(topic)
        if not readers:
            # No stream here reads the topic; ids still advance for the catch-up after a reconnect.
            self.last_id = max(self.last_id or 0, event_id)
            return
        for row in await self._fetch(_select("WHERE id = %s"), [event_id]):
            self._deliver(Message(*row))

    async def _catch_up(self) -> None:
        # LISTEN is active now, so events committed while it was not are in the table.
        if self.last_id is None:
            query = sql.SQL("SELECT coalesce(max(id), 0) FROM {}").format(_table())
            rows = await self._fetch(query, [])
            self.last_id = rows[0][0]
            return
        while True:
            messages = await self.replay([*self.queues, CLOSE_TOPIC], self.last_id)
            for message in messages:
                self._deliver(message)
            if len(messages) < REPLAY_BATCH:
                return

    def _close(self, target: str) -> None:
        for queue in self.by_target.get(target, set()) - self.revoked:
            self.revoked.add(queue)
            _replace_contents(queue, REVOKED)

    def _deliver(self, message: Message) -> None:
        # Ids become visible in order, so an id at or below last_id was delivered before.
        if self.last_id is not None and message.id <= self.last_id:
            return
        self.last_id = message.id
        if message.topic == CLOSE_TOPIC:
            self._close(message.html)
            return
        for queue in self.queues.get(message.topic, set()) - self.revoked:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                _replace_contents(queue, OVERFLOW)


def _discard(index: dict[str, set[asyncio.Queue]], keys, queue: asyncio.Queue) -> None:
    for key in keys:
        queues = index.get(key, set())
        queues.discard(queue)
        if not queues:
            index.pop(key, None)


def _replace_contents(queue: asyncio.Queue, sentinel: object) -> None:
    while not queue.empty():
        queue.get_nowait()
    queue.put_nowait(sentinel)


async def _closed_since(hub: Hub, owner: Owner, after_id: int) -> bool:
    """Whether close_streams() named the owner between authorisation and subscription."""
    while True:
        closes = await hub.replay([CLOSE_TOPIC], after_id)
        if any(close.html in owner.targets for close in closes):
            return True
        if len(closes) < REPLAY_BATCH:
            return False
        after_id = closes[-1].id


def _table() -> sql.Identifier:
    return sql.Identifier(StreamEvent._meta.db_table)


def _select(condition: str) -> sql.Composed:
    # condition is a literal from this module, never user input.
    query = "SELECT id, topic, event, html FROM {} " + condition
    return sql.SQL(query).format(_table())  # pyright: ignore[reportArgumentType]


_hubs: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Hub] = weakref.WeakKeyDictionary()


def get_hub() -> Hub:
    """The hub of the running event loop. Each granian worker runs one loop."""
    loop = asyncio.get_running_loop()
    if loop not in _hubs:
        _hubs[loop] = Hub()
    return _hubs[loop]


async def stream(request) -> HttpResponseBase:
    """`/events/?topic=a&topic=b`: one SSE stream for several topics, so a page needs one."""
    topics = request.GET.getlist("topic")
    if not topics:
        return HttpResponseBadRequest("Name at least one topic.")
    hub = get_hub()
    # Read before the check: a close committed after it has a larger id and is caught later.
    known = hub.last_id if hub.ready.is_set() else None
    authorized = await sync_to_async(_authorize)(request, topics, known)
    if authorized is None:
        return HttpResponseForbidden()
    owner, authorized_at = authorized
    last_event_id = parse_last_event_id(request.headers.get("Last-Event-ID", ""))
    messages = _messages(hub, topics, owner, authorized_at, last_event_id)
    response = StreamingHttpResponse(messages, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    return response


def _authorize(request, topics: list[str], known: int | None) -> tuple[Owner, int] | None:
    """The stream's owner and the newest event id before the check, if every topic is allowed.

    `known` is the hub's newest id. A hub that is not listening yet needs one query instead.
    """
    try:
        authorized_at = known
        if authorized_at is None and request.user.is_authenticated:
            authorized_at = StreamEvent.objects.aggregate(newest=Max("id"))["newest"] or 0
        if not all(can_subscribe(request, topic) for topic in topics):
            return None
        # Anonymous streams have no targets: close_streams() needs a user or a session login.
        if request.user.is_authenticated:
            owner = Owner.of(user=str(request.user.pk), session=request.session.session_key)
        else:
            owner = Owner(frozenset())
        return owner, authorized_at or 0
    finally:
        # Under ASGI this thread keeps its connection until the request ends, which for a
        # stream is when the client leaves. Closing returns it to the pool now.
        connection.close()


async def _messages(
    hub: Hub, topics: list[str], owner: Owner, authorized_at: int, last_event_id: int | None
):
    # Subscribed here, not in the view: a generator that never starts skips its finally.
    queue = hub.subscribe(topics, owner)
    sent = last_event_id or 0
    try:
        await hub.ready.wait()
        yield ": connected\n\n"
        # A close among the events since authorisation reached the hub before this queue existed.
        missed = (hub.last_id or 0) > authorized_at
        if owner.targets and missed and await _closed_since(hub, owner, authorized_at):
            yield CLOSED
            return
        if last_event_id is not None:
            replayed = await hub.replay(topics, sent)
            for message in replayed:
                sent = message.id
                yield format_event(message)
            if len(replayed) == REPLAY_BATCH:
                return
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if message is OVERFLOW:
                return
            if message is REVOKED:
                yield CLOSED
                return
            # The replay may already have sent what the queue collected meanwhile.
            if message.id <= sent:
                continue
            sent = message.id
            yield format_event(message)
    finally:
        hub.unsubscribe(topics, owner, queue)
