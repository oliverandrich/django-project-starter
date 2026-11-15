import io
import tempfile
from importlib import import_module
from pathlib import Path
from typing import Any
from unittest import mock, skipUnless

from crontask import utils
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, override_settings

scheduler_lock = import_module("{{ project_name }}.scheduler_lock")
PostgresLock = scheduler_lock.PostgresLock
SQLiteLock = scheduler_lock.SQLiteLock
UnlockedWarning = scheduler_lock.UnlockedWarning


class LockContract:
    """Tests every lock passes. Subclasses provide `lock()`."""

    def lock(self) -> Any:
        raise NotImplementedError

    def test_second_lock_fails_while_the_first_is_held(self: Any):
        with self.lock(), self.assertRaises(utils.LockError), self.lock():
            pass

    def test_lock_is_free_again_after_release(self: Any):
        with self.lock():
            pass
        with self.lock() as lock:
            self.assertTrue(lock.extend())


class SQLiteLockTest(LockContract, SimpleTestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = directory / "db.sqlite3.crontask.lock"

    def lock(self):
        return SQLiteLock(self.path, timeout=0.2)

    def test_crontask_reports_a_running_scheduler(self):
        stderr = io.StringIO()
        with self.lock(), mock.patch.object(utils, "lock", self.lock()):
            call_command("crontask", no_task_loading=True, no_heartbeat=True, stderr=stderr)
        self.assertIn("Another scheduler is already running.", stderr.getvalue())


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL")
class PostgresLockTest(LockContract, SimpleTestCase):
    def lock(self):
        return PostgresLock(connection.get_connection_params(), timeout=0.2)

    def test_extend_fails_once_the_session_is_gone(self):
        with self.lock() as lock:
            lock.handle.close()
            with self.assertRaises(utils.LockNotOwnedError):
                lock.extend()


class InstallTest(SimpleTestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(utils, "lock", utils.lock))

    def test_sqlite_gets_a_file_lock_next_to_the_database(self):
        vendor = mock.patch.object(connection, "vendor", "sqlite")
        name = mock.patch.dict(connection.settings_dict, {"NAME": "/srv/app/db.sqlite3"})
        with vendor, name:
            scheduler_lock.install()
        # Annotated: the lock classes come from import_module, so isinstance() narrows nothing.
        lock: Any = utils.lock
        self.assertIsInstance(lock, SQLiteLock)
        self.assertEqual(lock.path, Path("/srv/app/db.sqlite3.crontask.lock"))

    def test_postgresql_gets_an_advisory_lock(self):
        vendor = mock.patch.object(connection, "vendor", "postgresql")
        params = mock.patch.object(connection, "get_connection_params", return_value={})
        with vendor, params:
            scheduler_lock.install()
        self.assertIsInstance(utils.lock, PostgresLock)

    def test_other_vendors_run_unlocked_with_a_warning(self):
        with mock.patch.object(connection, "vendor", "mysql"):
            scheduler_lock.install()
        with self.assertLogs(scheduler_lock.logger, "WARNING"), utils.lock:
            pass
        self.assertIsInstance(utils.lock, UnlockedWarning)

    @override_settings(CRONTASK={"REDIS_URL": "redis://localhost:6379/0"})
    def test_redis_lock_is_kept(self):
        before = utils.lock
        scheduler_lock.install()
        self.assertIs(utils.lock, before)


class AppConfigTest(SimpleTestCase):
    def test_ready_installs_the_lock_for_the_database(self):
        locks = {"sqlite": SQLiteLock, "postgresql": PostgresLock}
        expected = locks.get(connection.vendor, UnlockedWarning)
        self.assertIsInstance(utils.lock, expected)
