from unittest import mock

from asgiref.sync import iscoroutinefunction
from django.db import OperationalError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils.module_loading import import_string

# A container health check connects to the loopback, which is not a public host name.
LOOPBACK = {"host": "127.0.0.1:8000"}
HEALTH = "{{ project_name }}.health"
HealthMiddleware = import_string(f"{HEALTH}.HealthMiddleware")


@override_settings(ALLOWED_HOSTS=["example.com"])
class LivenessTest(TestCase):
    def test_answers_ok(self):
        response = self.client.get("/health", headers=LOOPBACK)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_is_never_cached(self):
        response = self.client.get("/health", headers=LOOPBACK)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_reads_neither_database_nor_session(self):
        with self.assertNumQueries(0):
            response = self.client.get("/health", headers=LOOPBACK)
        self.assertNotIn("Vary", response)
        self.assertEqual(response.cookies, {})

    def test_answers_head(self):
        response = self.client.head("/health", headers=LOOPBACK)
        self.assertEqual(response.status_code, 200)


@override_settings(ALLOWED_HOSTS=["example.com"])
class ReadinessTest(TestCase):
    def test_answers_ok_when_database_and_cache_work(self):
        response = self.client.get("/health/ready", headers=LOOPBACK)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_answers_503_when_the_database_fails(self):
        with mock.patch(f"{HEALTH}.connection.cursor", side_effect=OperationalError):
            response = self.client.get("/health/ready", headers=LOOPBACK)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["checks"]["database"], "error")

    def test_answers_503_when_the_cache_fails(self):
        with mock.patch(f"{HEALTH}.cache.get", side_effect=OperationalError):
            response = self.client.get("/health/ready", headers=LOOPBACK)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["cache"], "error")

    def test_writes_nothing(self):
        with self.assertNumQueries(2):
            self.client.get("/health/ready", headers=LOOPBACK)


@override_settings(SECURE_SSL_REDIRECT=True)
class HealthOverHttpTest(TestCase):
    def test_answers_without_the_https_redirect(self):
        # The health check reaches the container over plain HTTP; Caddy terminates TLS.
        response = self.client.get("/health", headers=LOOPBACK)
        self.assertEqual(response.status_code, 200)


class AsyncChainTest(SimpleTestCase):
    def test_keeps_an_async_middleware_chain_async(self):
        async def get_response(request):
            return None

        middleware = HealthMiddleware(get_response)
        self.assertTrue(iscoroutinefunction(middleware))

    async def test_passes_other_paths_on_without_a_thread(self):
        response = object()

        async def get_response(request):
            return response

        middleware = HealthMiddleware(get_response)
        with mock.patch("asgiref.sync.SyncToAsync.__call__") as to_thread:
            result = await middleware(RequestFactory().get("/"))
        self.assertIs(result, response)
        to_thread.assert_not_called()

    async def test_answers_the_health_path_in_async_mode(self):
        async def get_response(request):
            raise AssertionError("the health path reached the rest of the stack")

        middleware = HealthMiddleware(get_response)
        response = await middleware(RequestFactory().get("/health"))
        self.assertEqual(response.status_code, 200)


class OtherPathsTest(TestCase):
    def test_leaves_other_paths_to_the_rest_of_the_stack(self):
        self.assertEqual(self.client.get("/health/other").status_code, 404)

    def test_leaves_other_methods_to_the_rest_of_the_stack(self):
        self.assertNotEqual(self.client.post("/health").status_code, 200)
