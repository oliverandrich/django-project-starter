import io
import tempfile
from contextlib import redirect_stdout
from importlib import import_module
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

worker = import_module("{{ project_name }}.management.commands.worker")

IMMEDIATE = {"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}}
DATABASE = {"default": {"BACKEND": "django_tasks_db.DatabaseBackend"}}


class WorkerCommandTest(SimpleTestCase):
    def setUp(self):
        base_dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(BASE_DIR=base_dir))
        self.run_db_worker = self.enterContext(mock.patch.object(worker, "call_command"))

    @override_settings(TASKS=DATABASE)
    def test_runs_db_worker_for_the_database_backend(self):
        call_command("worker")
        self.run_db_worker.assert_called_once_with("db_worker")

    @override_settings(TASKS=IMMEDIATE)
    def test_exits_without_a_worker_for_other_backends(self):
        with redirect_stdout(io.StringIO()) as stdout:
            call_command("worker")
        self.run_db_worker.assert_not_called()
        self.assertIn("No worker", stdout.getvalue())
