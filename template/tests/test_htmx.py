import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client, TestCase

VENDORED = ("vendor/htmx/htmx.min.js", "vendor/htmx/ext/hx-sse.min.js")


class HtmxTest(TestCase):
    def test_home_page_loads_the_vendored_scripts(self):
        response = self.client.get("/")
        for path in VENDORED:
            self.assertContains(response, f'<script src="{settings.STATIC_URL}{path}" defer>')

    def test_vendored_files_are_static_files(self):
        for path in VENDORED:
            self.assertIsNotNone(finders.find(path), path)

    def test_vendored_version_is_htmx_4(self):
        version = (Path(settings.BASE_DIR) / "assets/vendor/htmx/VERSION").read_text().strip()
        self.assertTrue(version.startswith("4."), version)

    def test_body_boosts_links_for_all_descendants(self):
        # htmx 4 passes attributes to descendants only with the :inherited suffix.
        self.assertContains(self.client.get("/"), 'hx-boost:inherited="true"')

    def test_csrf_header_follows_the_cookie(self):
        # A token fixed in the page goes stale when login() rotates it; the cookie does not.
        response = self.client.get("/")
        self.assertContains(response, "htmx:config:request")
        self.assertContains(response, "csrftoken=")

    def test_fallback_csrf_token_passes_the_csrf_check(self):
        client = Client(enforce_csrf_checks=True)
        page = client.get("/").content.decode()
        # Django renders a masked CSRF token as 64 alphanumeric characters.
        token = re.search(r'"([A-Za-z0-9]{64})"', page)
        assert token is not None, "base.html renders no fallback CSRF token"
        # 405 comes from the view, so CsrfViewMiddleware let the request through.
        response = client.post("/", headers={"X-CSRFToken": token[1]})
        self.assertEqual(response.status_code, 405)
