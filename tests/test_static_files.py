from collections.abc import Iterable

from django.http import FileResponse
from django.test import TestCase, override_settings


class DebugStaticFilesTest(TestCase):
    @override_settings(DEBUG=True)
    def test_debug_serves_app_static_files_without_collectstatic(self):
        # granian serves STATIC_ROOT only outside DEBUG; in DEBUG Django serves the app directories.
        response = self.client.get("/static/vendor/htmx/htmx.min.js")
        assert isinstance(response, FileResponse)
        content = response.streaming_content
        # Under the sync test client, FileResponse streams a sync iterator.
        assert isinstance(content, Iterable)
        self.assertIn(b"htmx", b"".join(content))

    def test_outside_debug_django_serves_no_static_files(self):
        self.assertEqual(self.client.get("/static/vendor/htmx/htmx.min.js").status_code, 404)
