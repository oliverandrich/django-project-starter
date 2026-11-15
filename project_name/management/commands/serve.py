"""Serve the project's ASGI application with Granian.

Granian reads further settings from GRANIAN_* environment variables, such as GRANIAN_WORKERS.
"""

import os
import sys
from pathlib import Path

import djclick as click
from django.conf import settings

# The project package, taken from this module's path. mise tasks cannot name it: mise.toml
# must not contain the placeholder.
PACKAGE = __name__.split(".", 1)[0]


# Plain djclick, not management.base: the process becomes granian, so a logfile stays empty.
@click.command()
@click.option("--reload", is_flag=True, help="Restart on Python changes in the project package.")
def main(reload):
    base_dir = Path(settings.BASE_DIR)
    argv = [
        sys.executable,
        "-m",
        "granian",
        f"{PACKAGE}.asgi:application",
        # Django has no ASGI lifespan support; asginl skips the handshake granian would log.
        "--interface",
        "asginl",
        "--no-ws",
        "--process-name",
        f"granian [{PACKAGE}]",
        "--working-dir",
        str(base_dir),
    ]
    if reload:
        argv += ["--reload", "--reload-paths", str(base_dir / PACKAGE)]
        # DEBUG reloads templates without a restart, and browser-reload refreshes the page.
        argv += ["--reload-ignore-dirs", "templates", "--reload-ignore-dirs", "locale"]
    # execv replaces the process, so unflushed output would be lost.
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, argv)
