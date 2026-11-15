"""Locks that keep one `manage.py crontask` scheduler running per database.

django-crontask locks through Redis or not at all. Without a lock, every running scheduler
enqueues every cron task. `install()` replaces `crontask.utils.lock` with a lock in the database
the project already uses. The `crontask` command enters that lock, calls `extend()` every
`LOCK_REFRESH_INTERVAL` seconds from a scheduler thread, and stops on `LockError`.

Both locks end with the process that holds them. The kernel releases a flock when its file closes.
PostgreSQL releases an advisory lock when its session ends. Neither lock needs a TTL. `extend()`
ignores the TTL arguments crontask passes.
"""

import logging
import time
from pathlib import Path
from typing import Any, Self

from crontask import conf, utils
from django.core.files import locks
from django.db import connection

logger = logging.getLogger(__name__)

# Advisory lock keys are scoped to the database, so a constant does not collide across projects
# with their own databases.
ADVISORY_LOCK_KEY = int.from_bytes(b"crontask", signed=True)

POLL_INTERVAL = 0.1


class _ProcessLock:
    """Polls `_try_lock()` on a handle until `timeout`. Closing the handle releases the lock."""

    handle: Any

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    def _open(self) -> Any:
        raise NotImplementedError

    def _try_lock(self) -> bool:
        raise NotImplementedError

    def __enter__(self) -> Self:
        self.handle = self._open()
        deadline = time.monotonic() + self.timeout
        while not self._try_lock():
            if time.monotonic() >= deadline:
                self.handle.close()
                raise utils.LockError("Another scheduler holds the lock.")
            time.sleep(POLL_INTERVAL)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.handle.close()


class SQLiteLock(_ProcessLock):
    """An exclusive `flock` on a file next to the SQLite database."""

    def __init__(self, path: Path, *, timeout: float) -> None:
        super().__init__(timeout=timeout)
        self.path = path

    def _open(self) -> Any:
        return self.path.open("a")

    def _try_lock(self) -> bool:
        return locks.lock(self.handle, locks.LOCK_EX | locks.LOCK_NB)

    def extend(self, *_ttl_args: object) -> bool:
        # A flock holds as long as its file stays open.
        return True


class PostgresLock(_ProcessLock):
    """A session-level advisory lock on a connection of its own.

    Not Django's connection: that one is thread-local, and `extend()` runs in a scheduler
    thread. A transaction-pooling PgBouncer breaks session-level locks.
    """

    def __init__(self, params: dict[str, Any], *, timeout: float) -> None:
        super().__init__(timeout=timeout)
        self.params = params

    def _open(self) -> Any:
        import psycopg

        return psycopg.connect(**self.params, autocommit=True)

    def _try_lock(self) -> bool:
        row = self.handle.execute(
            "SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_KEY,)
        ).fetchone()
        return bool(row and row[0])

    def extend(self, *_ttl_args: object) -> bool:
        # The lock lives as long as the session. A failed query means the session is gone.
        import psycopg

        try:
            self.handle.execute("SELECT 1")
        except psycopg.Error as error:
            raise utils.LockNotOwnedError("The scheduler lost its database session.") from error
        return True


class UnlockedWarning(utils.FakeLock):
    """No lock, for databases without one here. Warns when a scheduler starts."""

    def __enter__(self) -> Self:
        logger.warning(
            "No scheduler lock for the %s database. Run a single crontask process.",
            connection.vendor,
        )
        return self


def install() -> None:
    """Replace crontask's lock with one for the default database, unless Redis provides one."""
    # get_settings() builds its class with type(), so its attributes are invisible to type checkers.
    options: Any = conf.get_settings()
    if options.REDIS_URL:
        return
    timeout = options.LOCK_BLOCKING_TIMEOUT
    match connection.vendor:
        case "postgresql":
            # The stub declares None, the return type of the base class's abstract method.
            params: dict[str, Any] = connection.get_connection_params()  # pyright: ignore[reportAssignmentType]
            utils.lock = PostgresLock(params, timeout=timeout)
        case "sqlite":
            path = Path(f"{connection.settings_dict['NAME']}.crontask.lock")
            utils.lock = SQLiteLock(path, timeout=timeout)
        case _:
            utils.lock = UnlockedWarning()
