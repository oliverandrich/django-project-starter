import tempfile
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, override_settings


def database_exists(name: str) -> bool:
    # Private API, the same createdb uses, so the stubs leave it out.
    with connection._nodb_cursor() as cursor:  # pyright: ignore[reportAttributeAccessIssue]
        creation: Any = connection.creation
        return creation._database_exists(cursor, name)


class CreateDatabaseTest(SimpleTestCase):
    # The maintenance connection needs a reachable server, which the test database proves.
    databases = {"default"}

    def setUp(self):
        base_dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(BASE_DIR=base_dir))

    def test_creates_a_missing_database(self):
        name = f"test_createdb_{uuid.uuid4().hex[:12]}"
        self.addCleanup(self.drop_database, name)
        with mock.patch.dict(connection.settings_dict, {"NAME": name}):
            call_command("createdb")
        self.assertTrue(database_exists(name))

    def drop_database(self, name: str):
        with connection._nodb_cursor() as cursor:  # pyright: ignore[reportAttributeAccessIssue]
            cursor.execute(f"DROP DATABASE IF EXISTS {connection.ops.quote_name(name)}")

    def test_leaves_an_existing_database_alone(self):
        # The test database exists, so a CREATE DATABASE here would fail.
        call_command("createdb")

    def test_does_nothing_without_a_database_name(self):
        # A DATABASE_URL with only ?service=... leaves NAME empty.
        # The service file names the database then.
        with mock.patch.dict(connection.settings_dict, {"NAME": ""}):
            call_command("createdb")
