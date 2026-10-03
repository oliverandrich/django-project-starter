"""A command exercising every parameter shape management/base.py handles."""

from importlib import import_module

import djclick as click
from django.core.management import CommandError
from djclick.adapter import register_on_context

# A string, so the template repository stays valid Python before startproject renders it.
base = import_module("{{ project_name }}.management.base")
command, pass_logger = base.command, base.pass_logger


def hidden_option(*decls, **attrs):
    """An option the command reads from the context, like the common options."""
    return click.option(*decls, expose_value=False, callback=register_on_context, **attrs)


@command()
@click.argument("name")
@click.argument("extra", required=False, expose_value=False)
@click.option("--greeting", default="Hello")
@click.option("--shout", is_flag=True)
@click.option("--pretty/--plain", default=True)
@click.option("--fail", is_flag=True)
@hidden_option("--tag", multiple=True)
@hidden_option("--louder", count=True)
@hidden_option("--always", is_flag=True, default=True)
@pass_logger
def main(logger, name, greeting, shout, pretty, fail):
    if fail:
        raise CommandError("asked to fail")
    message = f"{greeting}, {name}"
    logger.info("%s pretty=%s", message.upper() if shout else message, pretty)
    logger.debug("debug detail")
