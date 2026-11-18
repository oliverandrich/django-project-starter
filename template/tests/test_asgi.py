from django.test import AsyncClient, TestCase


class AsgiTest(TestCase):
    async def test_home_page_renders_through_the_asgi_handler(self):
        # AsyncClient sends the request through Django's ASGIHandler and the full middleware stack.
        response = await AsyncClient().get("/")
        self.assertEqual(response.status_code, 200)
