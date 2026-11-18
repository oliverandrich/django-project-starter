import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from tests.utils import evaluate_settings

STORAGE = "{{ project_name }}.storage.HashedStaticFilesStorage"


class HashedStaticFilesStorageTest(SimpleTestCase):
    def test_settings_use_it(self):
        storages = evaluate_settings()["STORAGES"]
        self.assertEqual(storages["staticfiles"]["BACKEND"], STORAGE)

    def test_collectstatic_keeps_only_hashed_files(self):
        static_root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        storages = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": STORAGE},
        }
        with override_settings(STATIC_ROOT=static_root, STORAGES=storages):
            call_command("collectstatic", interactive=False, verbosity=0)
        htmx = sorted(path.name for path in (static_root / "vendor/htmx").glob("htmx.min*.js"))
        self.assertEqual(len(htmx), 1, htmx)
        self.assertRegex(htmx[0], r"^htmx\.min\.[0-9a-f]{12}\.js$")
        self.assertTrue((static_root / "staticfiles.json").is_file())
