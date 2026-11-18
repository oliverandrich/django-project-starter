import os
import runpy
from unittest import mock

from environs import Env

# manage.py sets it. settings.SETTINGS_MODULE is None under the test runner's override_settings.
SETTINGS_MODULE = os.environ["DJANGO_SETTINGS_MODULE"]
# The project package, such as acme_shop. Tests import its modules by this name.
PACKAGE = SETTINGS_MODULE.rpartition(".")[0]


def evaluate_settings(**environ: str) -> dict:
    """Evaluate the settings module against `environ` alone, without reading `.env`."""
    with mock.patch.dict(os.environ, environ, clear=True), mock.patch.object(Env, "read_env"):
        return runpy.run_module(SETTINGS_MODULE)
