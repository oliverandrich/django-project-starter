import os
import runpy
from unittest import mock

from environs import Env


def evaluate_settings(**environ: str) -> dict:
    """Evaluate the settings module against `environ` alone, without reading `.env`."""
    with mock.patch.dict(os.environ, environ, clear=True), mock.patch.object(Env, "read_env"):
        return runpy.run_module("{{ project_name }}.settings")
