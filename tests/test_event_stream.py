import asyncio
import functools
from collections.abc import AsyncIterable
from importlib import import_module
from typing import Any
from unittest import mock

from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sessions.backends.db import SessionStore
from django.db import connection, transaction
from django.http import StreamingHttpResponse
from django.test import AsyncClient, RequestFactory, SimpleTestCase, TransactionTestCase

events = import_module("{{ project_name }}.events")
StreamEvent = import_module("{{ project_name }}.models").StreamEvent


class CanSubscribeTest(SimpleTestCase):
    def request(self, user: Any):
        request = RequestFactory().get("/events/")
        request.user = user
        return request

    def test_anyone_may_read_public_topics(self):
        self.assertTrue(events.can_subscribe(self.request(AnonymousUser()), "public:news"))

    def test_a_user_topic_belongs_to_that_user_alone(self):
        user = User(pk=7)
        self.assertTrue(events.can_subscribe(self.request(user), "user:7"))
        self.assertFalse(events.can_subscribe(self.request(user), "user:8"))
        self.assertFalse(events.can_subscribe(self.request(AnonymousUser()), "user:7"))

    def test_other_topics_are_closed_until_the_project_opens_them(self):
        self.assertFalse(events.can_subscribe(self.request(User(pk=7)), "room:1"))


def terminate_listener():
    """Ends every hub's LISTEN session, as a database restart would."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE %s",
            ["LISTEN %"],
        )


def stops_the_hub(test):
    """Close the hub's connections in the test's own event loop.

    Django's test cases run no asyncTearDown, and the loop ends with the test.
    """

    @functools.wraps(test)
    async def wrapper(self):
        try:
            await test(self)
        finally:
            await events.get_hub().stop()

    return wrapper


class StreamTest(TransactionTestCase):
    async def open_stream(self, *topics: str, **headers: str):
        query = "&".join(f"topic={topic}" for topic in topics)
        response = await AsyncClient().get(f"/events/?{query}", headers=headers)
        assert isinstance(response, StreamingHttpResponse)
        content = response.streaming_content
        # An async view streams an async iterator, which granian sends without buffering.
        assert isinstance(content, AsyncIterable)
        return response, aiter(content)

    async def next_message(self, stream, timeout: float = 5) -> str:
        while True:
            chunk = await asyncio.wait_for(anext(stream), timeout)
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            if not text.startswith(":"):
                return text

    async def test_requires_a_topic(self):
        response = await AsyncClient().get("/events/")
        self.assertEqual(response.status_code, 400)

    async def test_refuses_a_topic_the_user_may_not_read(self):
        response = await AsyncClient().get("/events/?topic=public:news&topic=room:1")
        self.assertEqual(response.status_code, 403)

    @stops_the_hub
    async def test_delivers_a_broadcast_to_the_open_stream(self):
        response, stream = await self.open_stream("public:news")
        self.assertEqual(response["Content-Type"], "text/event-stream")
        await self.next_message_or_ready(stream)
        await sync_to_async(events.broadcast)("public:news", "<p>hi</p>")
        message = await self.next_message(stream)
        event = await StreamEvent.objects.aget()
        self.assertEqual(message, f"id: {event.id}\ndata: <p>hi</p>\n\n")

    @stops_the_hub
    async def test_other_topics_do_not_reach_the_stream(self):
        _, stream = await self.open_stream("public:news")
        await self.next_message_or_ready(stream)
        await sync_to_async(events.broadcast)("public:other", "<p>no</p>")
        await sync_to_async(events.broadcast)("public:news", "<p>yes</p>")
        self.assertIn("<p>yes</p>", await self.next_message(stream))

    @stops_the_hub
    async def test_last_event_id_replays_missed_events(self):
        seen = await StreamEvent.objects.acreate(topic="public:news", html="seen")
        missed = await StreamEvent.objects.acreate(topic="public:news", html="missed")
        await StreamEvent.objects.acreate(topic="public:other", html="elsewhere")
        _, stream = await self.open_stream("public:news", **{"Last-Event-ID": str(seen.id)})
        self.assertEqual(await self.next_message(stream), f"id: {missed.id}\ndata: missed\n\n")

    @stops_the_hub
    async def test_a_foreign_notify_leaves_the_listener_running(self):
        _, stream = await self.open_stream("public:news")
        await self.next_message_or_ready(stream)
        with self.assertLogs(events.logger, "WARNING"):
            await sync_to_async(self.notify)("ping")
            await sync_to_async(events.broadcast)("public:news", "<p>still</p>")
            self.assertIn("<p>still</p>", await self.next_message(stream))

    @stops_the_hub
    async def test_a_long_replay_ends_the_stream_after_one_batch(self):
        # htmx reconnects with the last id it got, so the next batch follows.
        first = await StreamEvent.objects.acreate(topic="public:news", html="one")
        await StreamEvent.objects.acreate(topic="public:news", html="two")
        await StreamEvent.objects.acreate(topic="public:news", html="three")
        with mock.patch.object(events, "REPLAY_BATCH", 1):
            _, stream = await self.open_stream("public:news", **{"Last-Event-ID": str(first.id)})
            self.assertIn("two", await self.next_message(stream))
            with self.assertRaises(StopAsyncIteration):
                await self.next_message(stream)

    @stops_the_hub
    async def test_an_unread_stream_leaves_no_subscription(self):
        request = RequestFactory().get("/events/?topic=public:news")
        request.user = AnonymousUser()
        request.session = SessionStore()
        response = await events.stream(request)
        await response.streaming_content.aclose()
        self.assertEqual(events.get_hub().queues, {})

    @stops_the_hub
    async def test_events_sent_while_the_listener_reconnects_arrive(self):
        _, stream = await self.open_stream("public:news")
        await self.next_message_or_ready(stream)
        with self.assertLogs(events.logger, "WARNING"):
            await sync_to_async(self.terminate_listener)()
            await sync_to_async(events.broadcast)("public:news", "<p>during</p>")
            self.assertIn("<p>during</p>", await self.next_message(stream, timeout=10))

    async def next_message_or_ready(self, stream):
        # The stream opens with a comment once its subscription is in place.
        chunk = await asyncio.wait_for(anext(stream), 5)
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        self.assertTrue(text.startswith(":"), text)

    def notify(self, payload):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_notify(%s, %s)", [events.CHANNEL, payload])

    def terminate_listener(self):
        terminate_listener()


class CloseStreamsTest(TransactionTestCase):
    async def logged_in_client(self, user) -> AsyncClient:
        client = AsyncClient()
        await client.aforce_login(user)
        return client

    async def open_stream(self, client: AsyncClient, topic: str):
        response = await client.get(f"/events/?topic={topic}")
        assert isinstance(response, StreamingHttpResponse)
        content = response.streaming_content
        assert isinstance(content, AsyncIterable)
        stream = aiter(content)
        ready = await asyncio.wait_for(anext(stream), 5)
        self.assertTrue(ready.startswith(b":"), ready)
        return stream

    async def next_message(self, stream, timeout: float = 5) -> bytes:
        while True:
            chunk = await asyncio.wait_for(anext(stream), timeout)
            if not chunk.startswith(b":"):
                return chunk

    async def assert_closed(self, stream):
        self.assertEqual(await self.next_message(stream), b"event: closed\ndata: \n\n")
        with self.assertRaises(StopAsyncIteration):
            await self.next_message(stream)

    @stops_the_hub
    async def test_logout_closes_the_streams_of_that_session_only(self):
        user = await User.objects.acreate_user("ada")
        first, second = await self.logged_in_client(user), await self.logged_in_client(user)
        first_stream = await self.open_stream(first, f"user:{user.pk}")
        second_stream = await self.open_stream(second, f"user:{user.pk}")
        await first.alogout()
        await self.assert_closed(first_stream)
        await sync_to_async(events.broadcast)(f"user:{user.pk}", "<p>still here</p>")
        self.assertIn(b"still here", await self.next_message(second_stream))

    @stops_the_hub
    async def test_closing_by_user_closes_every_session(self):
        user = await User.objects.acreate_user("ada")
        streams = [
            await self.open_stream(await self.logged_in_client(user), f"user:{user.pk}")
            for _ in range(2)
        ]
        await sync_to_async(events.close_streams)(user=user)
        for stream in streams:
            await self.assert_closed(stream)

    @stops_the_hub
    async def test_a_rolled_back_close_leaves_the_stream_open(self):
        user = await User.objects.acreate_user("ada")
        stream = await self.open_stream(await self.logged_in_client(user), f"user:{user.pk}")

        def close_then_roll_back():
            with transaction.atomic():
                events.close_streams(user=user)
                transaction.set_rollback(True)

        await sync_to_async(close_then_roll_back)()
        await sync_to_async(events.broadcast)(f"user:{user.pk}", "<p>open</p>")
        self.assertIn(b"open", await self.next_message(stream))

    @stops_the_hub
    async def test_a_close_sent_while_the_listener_reconnects_arrives(self):
        user = await User.objects.acreate_user("ada")
        stream = await self.open_stream(await self.logged_in_client(user), f"user:{user.pk}")
        with self.assertLogs(events.logger, "WARNING"):
            await sync_to_async(terminate_listener)()
            await sync_to_async(events.close_streams)(user=user)
            await self.assert_closed(stream)

    @stops_the_hub
    async def test_a_close_before_the_stream_starts_reaches_it(self):
        # The view authorises; the stream subscribes later, when its first chunk is read.
        user = await User.objects.acreate_user("ada")
        client = await self.logged_in_client(user)
        response = await client.get(f"/events/?topic=user:{user.pk}")
        assert isinstance(response, StreamingHttpResponse)
        content = response.streaming_content
        assert isinstance(content, AsyncIterable)
        await sync_to_async(events.close_streams)(user=user)
        stream = aiter(content)
        await self.assert_closed(stream)

    async def test_a_closed_stream_stays_closed_when_its_queue_overflows(self):
        hub = events.Hub()
        owner = events.Owner.of(user="7", session=None)
        with mock.patch.object(events, "QUEUE_SIZE", 2):
            queue = hub.subscribe(["public:news"], owner)
        try:
            hub._close("user:7")
            for event_id in range(1, 5):
                hub._deliver(events.Message(event_id, "public:news", "", "<p>x</p>"))
            self.assertEqual([queue.get_nowait() for _ in range(queue.qsize())], [events.REVOKED])
        finally:
            await hub.stop()

    async def test_a_process_without_targets_skips_loading_closes(self):
        hub = events.Hub()
        with mock.patch.object(hub, "_fetch") as fetch:
            await hub._receive(f"5:{events.CLOSE_TOPIC}")
        fetch.assert_not_called()
        self.assertEqual(hub.last_id, 5)


class CloseStreamsArgumentsTest(SimpleTestCase):
    def test_needs_a_user_or_a_session(self):
        with self.assertRaises(ValueError):
            events.close_streams()

    def test_a_session_without_a_key_has_no_streams(self):
        events.close_streams(session=SessionStore())
