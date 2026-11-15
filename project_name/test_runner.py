from django.conf import settings
from django.test import runner
from django.test.utils import override_settings
from django_rich.test import RichRunner


def suite_settings() -> override_settings:
    """Settings the whole suite runs under.

    The manifest storage fails every static lookup until `collectstatic` has run.
    A queueing task backend would leave enqueued tasks unrun.
    """
    staticfiles = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
    immediate = {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}
    return override_settings(
        STORAGES={**settings.STORAGES, "staticfiles": staticfiles},
        TASKS={**settings.TASKS, "default": immediate},
    )


def _use_suite_settings(*args):
    suite_settings().enable()


class ParallelTestSuite(runner.ParallelTestSuite):
    # Spawned workers import the settings afresh, so each one repeats the override.
    process_setup = _use_suite_settings


class TestRunner(RichRunner):
    parallel_test_suite = ParallelTestSuite

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        _use_suite_settings()
