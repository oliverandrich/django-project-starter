"""Database cache tables, created on migrate and made UNLOGGED."""

from django.core.cache import caches
from django.core.cache.backends.db import BaseDatabaseCache
from django.core.management import call_command
from django.db import connections


def create_cache_tables(using: str, **kwargs: object) -> None:
    """A post_migrate receiver, so every `migrate` leaves the cache usable."""
    # flush sends post_migrate too, but without a plan. It leaves the cache table alone.
    if "plan" not in kwargs:
        return
    call_command("createcachetable", database=using, verbosity=0)
    connection = connections[using]
    # The same selection createcachetable makes, including subclasses of DatabaseCache.
    tables = [
        cache._table  # pyright: ignore[reportAttributeAccessIssue]
        for cache in caches.all()
        if isinstance(cache, BaseDatabaseCache)
    ]
    with connection.cursor() as cursor:
        for table in tables:
            # to_regclass resolves the name as the cache backend's quoted identifier does.
            name = connection.ops.quote_name(table)
            cursor.execute(
                "SELECT relpersistence FROM pg_class WHERE oid = to_regclass(%s)", [name]
            )
            row = cursor.fetchone()
            # A cache holds nothing that must survive a crash. UNLOGGED skips the WAL on writes.
            if row and row[0] != "u":
                cursor.execute(f"ALTER TABLE {name} SET UNLOGGED")
