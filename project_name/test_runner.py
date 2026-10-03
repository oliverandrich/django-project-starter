from django.conf import settings
from django.test import runner
from django.test.utils import override_settings
from django_rich.test import RichRunner


def _use_plain_staticfiles(*args):
    """Swap the manifest storage, which fails every static lookup until `collectstatic` has run."""
    staticfiles = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
    override_settings(STORAGES={**settings.STORAGES, "staticfiles": staticfiles}).enable()


class ParallelTestSuite(runner.ParallelTestSuite):
    # Spawned workers import the settings afresh, so each one repeats the swap.
    process_setup = _use_plain_staticfiles


class TestRunner(RichRunner):
    parallel_test_suite = ParallelTestSuite

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        _use_plain_staticfiles()
