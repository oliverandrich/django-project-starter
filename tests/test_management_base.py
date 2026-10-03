import tempfile
from pathlib import Path

from django.core import checks
from django.core.management import CommandError, call_command
from django.core.management.base import SystemCheckError
from django.test import SimpleTestCase, modify_settings, override_settings


@modify_settings(INSTALLED_APPS={"append": "tests"})
class LoggingCommandTest(SimpleTestCase):
    def setUp(self):
        base_dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(override_settings(BASE_DIR=base_dir))
        self.logfile = base_dir / "logs" / "probe.log"

    def log(self):
        return self.logfile.read_text()

    def test_writes_to_logfile(self):
        call_command("probe", "World")
        self.assertIn("Hello, World pretty=True", self.log())

    def test_option_by_keyword(self):
        call_command("probe", "World", greeting="Hi")
        self.assertIn("Hi, World", self.log())

    def test_flag_by_keyword(self):
        call_command("probe", "World", shout=True)
        self.assertIn("HELLO, WORLD", self.log())

    def test_flag_off_through_secondary_form(self):
        call_command("probe", "World", pretty=False)
        self.assertIn("pretty=False", self.log())

    def test_verbosity_sets_log_level(self):
        call_command("probe", "World", verbosity=0)
        self.assertNotIn("debug detail", self.log())
        call_command("probe", "World", verbosity=2)
        self.assertIn("debug detail", self.log())

    def test_short_option_alias(self):
        call_command("probe", "World", v=2)
        self.assertIn("debug detail", self.log())

    def test_repeated_runs_do_not_stack_handlers(self):
        call_command("probe", "World", greeting="First")
        call_command("probe", "World", greeting="Second")
        self.assertEqual(self.log().count("Second, World"), 1)

    def test_command_error_propagates(self):
        with self.assertRaisesMessage(CommandError, "asked to fail"):
            call_command("probe", "World", fail=True)

    def test_refuses_hidden_parameters_without_an_argv_form(self):
        for kwargs in ({"extra": "x"}, {"tag": ["a"]}, {"louder": 1}, {"always": False}):
            with self.subTest(kwargs=kwargs), self.assertRaises(TypeError):
                call_command("probe", "World", **kwargs)

    def test_system_checks_run_only_when_asked(self):
        def failing_check(**kwargs):
            return [checks.Error("probe failure", id="tests.E001")]

        checks.register(failing_check)
        self.addCleanup(checks.registry.registry.registered_checks.discard, failing_check)

        call_command("probe", "World")
        with self.assertRaises(SystemCheckError):
            call_command("probe", "World", skip_checks=False)

    def test_pass_logger_needs_the_command_decorator(self):
        with self.assertRaisesMessage(RuntimeError, "@pass_logger needs the @command()"):
            call_command("unprepared")
