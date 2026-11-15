import sys
from importlib import import_module
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase

serve = import_module("{{ project_name }}.management.commands.serve")

PACKAGE = "{{ project_name }}"


class ServeCommandTest(SimpleTestCase):
    def setUp(self):
        self.execv = self.enterContext(mock.patch.object(serve.os, "execv"))

    def argv(self) -> list[str]:
        executable, argv = self.execv.call_args.args
        self.assertEqual(executable, sys.executable)
        return argv

    def option(self, argv: list[str], name: str) -> list[str]:
        return [argv[i + 1] for i, arg in enumerate(argv) if arg == name]

    def test_runs_the_asgi_application_under_granian(self):
        call_command("serve")
        argv = self.argv()
        self.assertEqual(argv[:4], [sys.executable, "-m", "granian", f"{PACKAGE}.asgi:application"])
        self.assertEqual(self.option(argv, "--interface"), ["asginl"])
        self.assertNotIn("--reload", argv)

    def test_imports_the_application_from_the_project_root(self):
        # The target resolves against --working-dir, not the shell's current directory.
        call_command("serve")
        self.assertEqual(self.option(self.argv(), "--working-dir"), [str(settings.BASE_DIR)])

    def test_reload_watches_python_code_in_the_project_package(self):
        call_command("serve", "--reload")
        argv = self.argv()
        self.assertIn("--reload", argv)
        package_dir = str(Path(settings.BASE_DIR) / PACKAGE)
        self.assertEqual(self.option(argv, "--reload-paths"), [package_dir])
        # DEBUG reloads templates without a restart; browser-reload refreshes the page.
        ignored = self.option(argv, "--reload-ignore-dirs")
        self.assertEqual(sorted(ignored), ["locale", "templates"])
