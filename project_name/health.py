"""Liveness and readiness endpoints, answered before host validation, sessions and CSRF.

A container health check reaches the server on the loopback, whose address is not in
ALLOWED_HOSTS. The paths are fixed and carry no data, so skipping the host check is safe.
"""

from collections.abc import Awaitable, Callable

from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.cache import patch_cache_control

CACHE_KEY = "health:ready"


def live() -> JsonResponse:
    return _no_store(JsonResponse({"status": "ok"}))


def ready() -> JsonResponse:
    checks = {"database": _check(_database), "cache": _check(_cache)}
    healthy = all(result == "ok" for result in checks.values())
    response = JsonResponse(
        {"status": "ok" if healthy else "error", "checks": checks},
        status=200 if healthy else 503,
    )
    return _no_store(response)


def _database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def _cache() -> None:
    # A read reaches the cache backend without a write on every probe.
    cache.get(CACHE_KEY)


def _check(probe: Callable[[], None]) -> str:
    try:
        probe()
    except Exception:  # noqa: BLE001 - any failure means not ready
        return "error"
    return "ok"


def _no_store(response: JsonResponse) -> JsonResponse:
    patch_cache_control(response, no_store=True)
    return response


ENDPOINTS = {"/health": live, "/health/ready": ready}


def _endpoint(request: HttpRequest) -> Callable[[], JsonResponse] | None:
    if request.method in ("GET", "HEAD"):
        return ENDPOINTS.get(request.path_info)
    return None


class HealthMiddleware:
    """Answers the health paths. MIDDLEWARE lists it before every other middleware."""

    sync_capable = True
    async_capable = True

    def __init__(
        self, get_response: Callable[[HttpRequest], HttpResponse | Awaitable[HttpResponse]]
    ) -> None:
        self.get_response = get_response
        self.async_mode = iscoroutinefunction(get_response)
        if self.async_mode:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest):
        if self.async_mode:
            return self.__acall__(request)
        endpoint = _endpoint(request)
        return endpoint() if endpoint else self.get_response(request)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        endpoint = _endpoint(request)
        if endpoint is None:
            # Other requests reach the rest of the chain without a hop into a thread.
            return await self.get_response(request)  # pyright: ignore[reportGeneralTypeIssues]
        # The readiness probes query the database, which needs sync code.
        return await sync_to_async(endpoint)()
