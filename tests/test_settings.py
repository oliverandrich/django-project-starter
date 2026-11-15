from django.core.files.storage import FileSystemStorage, default_storage
from django.test import SimpleTestCase

from tests.utils import evaluate_settings


class StoragesTest(SimpleTestCase):
    def test_default_storage_is_configured(self):
        # Setting STORAGES replaces Django's defaults, so "default" must be listed explicitly.
        self.assertIsInstance(default_storage, FileSystemStorage)


class DatabaseSettingTest(SimpleTestCase):
    def test_local_postgresql_by_default(self):
        database = evaluate_settings()["DATABASES"]["default"]
        self.assertEqual(database["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(database["NAME"], "{{ project_name }}")

    def test_database_url_selects_the_database(self):
        url = "postgres://app:secret@db.example.com:5433/shop"
        database = evaluate_settings(DATABASE_URL=url)["DATABASES"]["default"]
        self.assertEqual(
            (database["HOST"], database["PORT"], database["NAME"], database["USER"]),
            ("db.example.com", 5433, "shop", "app"),
        )

    def test_connection_pool_by_default(self):
        database = evaluate_settings()["DATABASES"]["default"]
        self.assertEqual(database["OPTIONS"]["pool"], {"min_size": 1, "max_size": 10})

    def test_pool_size_comes_from_the_environment(self):
        environ = {"DATABASE_POOL_MIN_SIZE": "2", "DATABASE_POOL_MAX_SIZE": "20"}
        database = evaluate_settings(**environ)["DATABASES"]["default"]
        self.assertEqual(database["OPTIONS"]["pool"], {"min_size": 2, "max_size": 20})

    def test_database_pool_turns_the_pool_off(self):
        # PgBouncer in transaction mode needs Django's pool off.
        database = evaluate_settings(DATABASE_POOL="false")["DATABASES"]["default"]
        self.assertNotIn("pool", database.get("OPTIONS", {}))


class EventsSettingTest(SimpleTestCase):
    def test_retention_defaults_to_a_day(self):
        self.assertEqual(evaluate_settings()["EVENTS_RETENTION_HOURS"], 24)

    def test_retention_comes_from_the_environment(self):
        self.assertEqual(
            evaluate_settings(EVENTS_RETENTION_HOURS="72")["EVENTS_RETENTION_HOURS"], 72
        )
