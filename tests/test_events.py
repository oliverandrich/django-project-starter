import threading
from importlib import import_module
from unittest import mock

import psycopg
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from psycopg import sql

events = import_module("{{ project_name }}.events")
StreamEvent = import_module("{{ project_name }}.models").StreamEvent


def listener() -> psycopg.Connection:
    """A connection of its own that receives the NOTIFY broadcast() sends."""
    conn = psycopg.connect(**events.connect_params(), autocommit=True)
    conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(events.CHANNEL)))
    return conn


def notified_ids(conn: psycopg.Connection, count: int) -> list[int]:
    notifies = conn.notifies(timeout=5, stop_after=count)
    received = [int(n.payload.split(":", 1)[0]) for n in notifies]
    return received


class FormatTest(SimpleTestCase):
    def test_single_line(self):
        event = StreamEvent(id=7, topic="public:news", html="<p>hi</p>")
        self.assertEqual(events.format_event(event), "id: 7\ndata: <p>hi</p>\n\n")

    def test_each_line_gets_a_data_field(self):
        event = StreamEvent(id=8, topic="public:news", html="<ul>\n<li>a</li>\n</ul>")
        self.assertEqual(
            events.format_event(event), "id: 8\ndata: <ul>\ndata: <li>a</li>\ndata: </ul>\n\n"
        )

    def test_named_event(self):
        event = StreamEvent(id=9, topic="user:1", event="progress", html="50")
        self.assertEqual(events.format_event(event), "id: 9\nevent: progress\ndata: 50\n\n")

    def test_a_carriage_return_cannot_start_a_field(self):
        # SSE ends a line at CR, LF or CRLF; user text with a lone CR must stay data.
        event = StreamEvent(id=10, topic="public:news", html="a\rid: 999\r\nb")
        expected = "id: 10\ndata: a\ndata: id: 999\ndata: b\n\n"
        self.assertEqual(events.format_event(event), expected)

    def test_event_names_reject_line_breaks(self):
        with self.assertRaises(ValueError):
            events.broadcast("public:news", "x", event="a\ndata: b")

    def test_payload_carries_id_and_topic(self):
        self.assertEqual(events.parse_payload("12:room:3"), (12, "room:3"))
        self.assertIsNone(events.parse_payload("ping"))

    def test_last_event_id_must_be_a_plain_number(self):
        self.assertEqual(events.parse_last_event_id("42"), 42)
        for value in ("", "abc", "²", "-1"):
            self.assertIsNone(events.parse_last_event_id(value), value)


class BroadcastTest(TestCase):
    def test_writes_the_event_when_the_transaction_commits(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            events.broadcast("public:news", "<p>hi</p>")
            self.assertFalse(StreamEvent.objects.exists())
        self.assertEqual(len(callbacks), 1)
        event = StreamEvent.objects.get()
        self.assertEqual((event.topic, event.html, event.event), ("public:news", "<p>hi</p>", ""))

    def test_a_failed_publish_is_logged_not_raised(self):
        # The caller's transaction has committed; a 500 would invite a duplicate retry.
        failure = mock.patch.object(StreamEvent.objects, "create", side_effect=RuntimeError("down"))
        # Production logs to django.db.backends.base; captureOnCommitCallbacks to django.test.
        with failure, self.assertLogs("django", "ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                events.broadcast("public:news", "<p>hi</p>")

    def test_a_rollback_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                events.broadcast("public:news", "<p>hi</p>")
                raise RuntimeError
        self.assertFalse(StreamEvent.objects.exists())


class NotifyTest(TransactionTestCase):
    def test_notifies_listeners_with_the_event_id(self):
        conn = self.enterContext(listener())
        events.broadcast("public:news", "<p>hi</p>")
        self.assertEqual(notified_ids(conn, 1), [StreamEvent.objects.get().id])

    def test_events_become_visible_in_id_order(self):
        # Replay after Last-Event-ID is exact only if no smaller id commits after a larger one.
        conn = self.enterContext(listener())
        first_holds_the_lock = threading.Event()
        original_notify = events._notify

        def slow_notify(*args):
            if not first_holds_the_lock.is_set():
                first_holds_the_lock.set()
                threading.Event().wait(0.5)
            original_notify(*args)

        def send(text):
            events.broadcast("public:news", text)
            connection.close()

        with mock.patch.object(events, "_notify", slow_notify):
            first = threading.Thread(target=send, args=("first",))
            first.start()
            first_holds_the_lock.wait(5)
            second = threading.Thread(target=send, args=("second",))
            second.start()
            first.join()
            second.join()

        received = notified_ids(conn, 2)
        self.assertEqual(received, sorted(received))
        ids = dict(StreamEvent.objects.values_list("html", "id"))
        self.assertLess(ids["first"], ids["second"])
