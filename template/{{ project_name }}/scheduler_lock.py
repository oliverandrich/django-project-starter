"""A PostgreSQL lock that keeps one `manage.py crontask` scheduler running per database.

django-crontask locks through Redis or not at all. Without a lock, every running scheduler
enqueues every cron task. `install()` replaces `crontask.utils.lock` with an advisory lock.
The `crontask` command enters that lock, calls `extend()` every `LOCK_REFRESH_INTERVAL`
seconds from a scheduler thread, and stops on `LockError`.

PostgreSQL releases an advisory lock when its session ends, so the lock needs no TTL.
`extend()` ignores the TTL arguments crontask passes.
"""

import time
from typing import Any, Self

import psycopg
from crontask import conf, utils
from django.db import connection

# Advisory lock keys are scoped to the database, so a constant does not collide across projects
# with their own databases.
ADVISORY_LOCK_KEY = int.from_bytes(b"crontask", signed=True)

POLL_INTERVAL = 0.1


class PostgresLock:
    """A session-level advisory lock on a connection of its own.

    Not Django's connection: that one is thread-local, and `extend()` runs in a scheduler
    thread. A transaction-pooling PgBouncer breaks session-level locks.
    """

    def __init__(self, params: dict[str, Any], *, timeout: float) -> None:
        self.params = params
        self.timeout = timeout

    def _try_lock(self) -> bool:
        row = self.connection.execute(
            "SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_KEY,)
        ).fetchone()
        return bool(row and row[0])

    def __enter__(self) -> Self:
        self.connection = psycopg.connect(**self.params, autocommit=True)
        try:
            deadline = time.monotonic() + self.timeout
            while not self._try_lock():
                if time.monotonic() >= deadline:
                    raise utils.LockError("Another scheduler holds the lock.")
                time.sleep(POLL_INTERVAL)
        except BaseException:
            self.connection.close()
            raise
        return self

    def __exit__(self, *exc_info: object) -> None:
        # Closing the session releases the advisory lock.
        self.connection.close()

    def extend(self, *_ttl_args: object) -> bool:
        # The lock lives as long as the session. A failed query means the session is gone.
        try:
            self.connection.execute("SELECT 1")
        except psycopg.Error as error:
            raise utils.LockNotOwnedError("The scheduler lost its database session.") from error
        return True


def install() -> None:
    """Replace crontask's lock with an advisory lock, unless Redis provides one."""
    # get_settings() builds its class with type(), so its attributes are invisible to type checkers.
    options: Any = conf.get_settings()
    if options.REDIS_URL:
        return
    # The stub declares None, the return type of the base class's abstract method.
    params: dict[str, Any] = connection.get_connection_params()  # pyright: ignore[reportAssignmentType]
    utils.lock = PostgresLock(params, timeout=options.LOCK_BLOCKING_TIMEOUT)
