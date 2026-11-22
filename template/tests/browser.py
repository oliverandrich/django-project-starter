"""The base of the browser tests, which run in Chromium with `mise run test-browser`."""

import os
from importlib import import_module
from unittest import mock

from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag
from playwright.sync_api import sync_playwright


@tag("browser")
class BrowserTestCase(StaticLiveServerTestCase):
    """One Chromium page per test. An uncaught error on the page fails the test."""

    @classmethod
    def setUpClass(cls):
        # Playwright's sync API runs an event loop in this thread, and Django refuses ORM calls
        # next to one. The variable is process-wide, so the live server skips that check too.
        environ = mock.patch.dict(os.environ, {"DJANGO_ALLOW_ASYNC_UNSAFE": "true"})
        environ.start()
        cls.addClassCleanup(environ.stop)
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.chromium.launch()
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        # LocaleMiddleware follows the browser's language; the tests look for English labels.
        self.context = self.browser.new_context(locale="en-US")
        self.page = self.context.new_page()
        self.page.set_default_timeout(10_000)
        self.page_errors: list[str] = []
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.page_errors, [])

    def url(self, path: str) -> str:
        return f"{self.live_server_url}{path}"

    def logged_in_user(self):
        """The account of the browser's session cookie, or None."""
        for cookie in self.context.cookies(self.live_server_url):
            if cookie.get("name") == settings.SESSION_COOKIE_NAME:
                store = import_module(settings.SESSION_ENGINE).SessionStore(cookie.get("value"))
                user_id = store.get(SESSION_KEY)
                return get_user_model().objects.filter(pk=user_id).first()
        return None
