import os
import sys
import tempfile
from importlib import import_module
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from tests.utils import PACKAGE

serve = import_module(f"{PACKAGE}.management.commands.serve")


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

    def test_reload_watches_the_whole_project_package(self):
        call_command("serve", "--reload")
        argv = self.argv()
        self.assertIn("--reload", argv)
        package_dir = str(Path(settings.BASE_DIR) / PACKAGE)
        self.assertEqual(self.option(argv, "--reload-paths"), [package_dir])
        # Templates and translations restart the worker too: only runserver clears Django's
        # template cache, and browser-reload refreshes the page after a restart.
        self.assertEqual(self.option(argv, "--reload-ignore-dirs"), [])

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


class KillTimeoutTest(SimpleTestCase):
    """granian waits without limit for open responses, and a server-sent event stream stays open."""

    def setUp(self):
        self.environ = self.enterContext(mock.patch.dict(serve.os.environ))
        self.environ.pop("GRANIAN_WORKERS_KILL_TIMEOUT", None)
        self.execv = self.enterContext(mock.patch.object(serve.os, "execv"))

    def kill_timeout(self, *args: str) -> str | None:
        seen = {}
        self.execv.side_effect = lambda *_: seen.update(os.environ)
        call_command("serve", *args)
        return seen.get("GRANIAN_WORKERS_KILL_TIMEOUT")

    def test_serving_kills_stuck_workers_before_docker_does(self):
        # Docker sends SIGKILL 10 seconds after SIGTERM by default.
        self.assertEqual(self.kill_timeout(), "5")

    def test_reloading_kills_stuck_workers_at_once(self):
        self.assertEqual(self.kill_timeout("--reload"), "1")

    def test_the_environment_overrides_the_default(self):
        self.environ["GRANIAN_WORKERS_KILL_TIMEOUT"] = "30"
        self.assertEqual(self.kill_timeout(), "30")

    def test_no_option_overrides_the_environment(self):
        # A command-line option takes precedence over granian's environment variable.
        call_command("serve")
        self.assertNotIn("--workers-kill-timeout", self.execv.call_args.args[1])


class BackpressureTest(SimpleTestCase):
    """granian serves GRANIAN_BACKPRESSURE requests per worker at once; an open stream is one."""

    def setUp(self):
        self.environ = self.enterContext(mock.patch.dict(serve.os.environ))
        self.environ.pop("GRANIAN_BACKPRESSURE", None)
        self.execv = self.enterContext(mock.patch.object(serve.os, "execv"))

    def backpressure(self) -> str | None:
        seen = {}
        self.execv.side_effect = lambda *_: seen.update(os.environ)
        call_command("serve")
        return seen.get("GRANIAN_BACKPRESSURE")

    def test_a_worker_holds_more_streams_than_granians_default(self):
        # granian's default, a backlog of 1024 divided by the workers, would hold few open streams.
        self.assertEqual(self.backpressure(), "8192")

    def test_the_environment_overrides_the_default(self):
        self.environ["GRANIAN_BACKPRESSURE"] = "2048"
        self.assertEqual(self.backpressure(), "2048")

    def test_no_option_overrides_the_environment(self):
        call_command("serve")
        self.assertNotIn("--backpressure", self.execv.call_args.args[1])
