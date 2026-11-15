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
from django.http import HttpResponseBadRequest, HttpResponseForbidden, StreamingHttpResponse
from django.http.response import HttpResponseBase
from psycopg import sql

# A string, so the template repository stays valid Python before startproject renders it.
StreamEvent = import_module("{{ project_name }}.models").StreamEvent

logger = logging.getLogger(__name__)

CHANNEL = "sse"
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
CLOSE = object()


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
        self.ready = asyncio.Event()
        self.last_id: int | None = None
        self.task: asyncio.Task | None = None
        self.fetch_connection: psycopg.AsyncConnection | None = None
        self.fetch_lock = asyncio.Lock()

    def subscribe(self, topics: list[str]) -> asyncio.Queue:
        """A queue that receives the events of `topics`. Starts the listener on first use."""
        queue: asyncio.Queue = asyncio.Queue(QUEUE_SIZE)
        for topic in topics:
            self.queues.setdefault(topic, set()).add(queue)
        if self.task is None or self.task.done():
            self.task = asyncio.get_running_loop().create_task(self._listen())
        return queue

    def unsubscribe(self, topics: list[str], queue: asyncio.Queue) -> None:
        for topic in topics:
            queues = self.queues.get(topic, set())
            queues.discard(queue)
            if not queues:
                self.queues.pop(topic, None)

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
        if topic not in self.queues:
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
            messages = await self.replay(list(self.queues), self.last_id)
            for message in messages:
                self._deliver(message)
            if len(messages) < REPLAY_BATCH:
                return

    def _deliver(self, message: Message) -> None:
        # Ids become visible in order, so an id at or below last_id was delivered before.
        if self.last_id is not None and message.id <= self.last_id:
            return
        self.last_id = message.id
        for queue in self.queues.get(message.topic, set()):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(CLOSE)


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
    if not await sync_to_async(_may_subscribe)(request, topics):
        return HttpResponseForbidden()
    last_event_id = parse_last_event_id(request.headers.get("Last-Event-ID", ""))
    response = StreamingHttpResponse(
        _messages(get_hub(), topics, last_event_id), content_type="text/event-stream"
    )
    response["Cache-Control"] = "no-cache"
    return response


def _may_subscribe(request, topics: list[str]) -> bool:
    try:
        return all(can_subscribe(request, topic) for topic in topics)
    finally:
        # Under ASGI this thread keeps its connection until the request ends, which for a
        # stream is when the client leaves. Closing returns it to the pool now.
        connection.close()


async def _messages(hub: Hub, topics: list[str], last_event_id: int | None):
    # Subscribed here, not in the view: a generator that never starts skips its finally.
    queue = hub.subscribe(topics)
    sent = last_event_id or 0
    try:
        await hub.ready.wait()
        yield ": connected\n\n"
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
            if message is CLOSE:
                return
            # The replay may already have sent what the queue collected meanwhile.
            if message.id <= sent:
                continue
            sent = message.id
            yield format_event(message)
    finally:
        hub.unsubscribe(topics, queue)
