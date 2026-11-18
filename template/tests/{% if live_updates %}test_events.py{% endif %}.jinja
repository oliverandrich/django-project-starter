from importlib import import_module
from typing import Any

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from django.utils.module_loading import import_string

# A string, so the template repository stays valid Python before startproject renders it.
events = import_module("{{ project_name }}.events")


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


class WiringTest(SimpleTestCase):
    def test_the_stream_lives_at_events(self):
        self.assertEqual(reverse("pg_sse:stream"), "/events/")

    def test_the_project_policy_decides_who_reads_a_topic(self):
        policy = import_string(settings.PG_SSE["CAN_SUBSCRIBE"])
        self.assertIs(policy, events.can_subscribe)
