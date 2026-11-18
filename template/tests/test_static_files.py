from collections.abc import AsyncIterable

from django.http import StreamingHttpResponse
from django.test import AsyncClient, TestCase, override_settings


class DebugStaticFilesTest(TestCase):
    @override_settings(DEBUG=True)
    async def test_debug_serves_app_static_files_without_collectstatic(self):
        # granian serves STATIC_ROOT only outside DEBUG; in DEBUG Django serves the app directories.
        response = await AsyncClient().get("/static/vendor/htmx/htmx.min.js")
        assert isinstance(response, StreamingHttpResponse)
        content = response.streaming_content
        # Django's ASGI handler warns about every response that streams a synchronous iterator.
        assert isinstance(content, AsyncIterable)
        body = b"".join([chunk async for chunk in content])
        self.assertIn(b"htmx", body)

    def test_outside_debug_django_serves_no_static_files(self):
        self.assertEqual(self.client.get("/static/vendor/htmx/htmx.min.js").status_code, 404)
