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
