"""A plain django-click command, which never sets up the logger pass_logger needs."""

from importlib import import_module

import djclick as click
from tests.utils import PACKAGE

# A string, so the template repository stays valid Python before startproject renders it.
pass_logger = import_module(f"{PACKAGE}.management.base").pass_logger


@click.command()
@pass_logger
def main(logger):
    logger.info("unreachable")
