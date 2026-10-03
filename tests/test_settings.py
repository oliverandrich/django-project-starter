from django.core.files.storage import FileSystemStorage, default_storage
from django.test import SimpleTestCase


class StoragesTest(SimpleTestCase):
    def test_default_storage_is_configured(self):
        # Setting STORAGES replaces Django's defaults, so "default" must be listed explicitly.
        self.assertIsInstance(default_storage, FileSystemStorage)
