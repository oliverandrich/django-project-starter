import asyncio
import functools
from collections.abc import AsyncIterable
from importlib import import_module
from typing import Any
from unittest import mock

from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser, User
from django.db import connection
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
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query = %s",
                [f'LISTEN "{events.CHANNEL}"'],
            )
