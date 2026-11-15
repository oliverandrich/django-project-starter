import sys
import tempfile
from importlib import import_module
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

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

    def test_granian_serves_static_files_outside_debug(self):
        static_root = self.enterContext(tempfile.TemporaryDirectory())
        with override_settings(DEBUG=False, STATIC_ROOT=static_root):
            call_command("serve")
        argv = self.argv()
        self.assertEqual(self.option(argv, "--static-path-route"), ["/static"])
        self.assertEqual(self.option(argv, "--static-path-mount"), [static_root])
        # Only hashed files remain after collectstatic, so a year cannot serve a stale file.
        self.assertEqual(self.option(argv, "--static-path-expires"), ["31536000"])

    @override_settings(DEBUG=False, STATIC_ROOT="/nonexistent/static")
    def test_a_missing_static_root_is_not_mounted(self):
        # granian refuses to start with a mount that does not exist.
        with self.assertWarnsRegex(RuntimeWarning, "collectstatic"):
            call_command("serve")
        self.assertNotIn("--static-path-mount", self.argv())

    @override_settings(DEBUG=False, STATIC_URL="https://cdn.example.com/static/")
    def test_static_files_on_another_host_are_not_mounted(self):
        call_command("serve")
        self.assertNotIn("--static-path-mount", self.argv())

    @override_settings(DEBUG=True)
    def test_debug_leaves_static_files_to_django(self):
        # Django serves the app directories through the finders, without collectstatic.
        call_command("serve")
        self.assertNotIn("--static-path-mount", self.argv())
