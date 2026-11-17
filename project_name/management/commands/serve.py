"""Serve the project's ASGI application with Granian.

Granian reads further settings from GRANIAN_* environment variables, such as GRANIAN_WORKERS.
"""

import os
import sys
import warnings
from pathlib import Path
from urllib.parse import urlsplit

import djclick as click
from django.conf import settings

# The project package, taken from this module's path. mise tasks cannot name it: mise.toml
# must not contain the placeholder.
PACKAGE = __name__.split(".", 1)[0]

# One year. Every collected file carries its content hash, see storage.py.
STATIC_EXPIRES = 365 * 24 * 60 * 60

# Seconds granian waits for a worker to stop before it kills it. granian waits without limit by
# default, and a server-sent event stream stays open. 5 is below Docker's 10-second stop timeout.
KILL_TIMEOUT = "5"
RELOAD_KILL_TIMEOUT = "1"


# Plain djclick, not management.base: the process becomes granian, so a logfile stays empty.
def _static_files_options() -> list[str]:
    # In DEBUG, Django serves the app directories, so collectstatic is not needed.
    if urlsplit(settings.STATIC_URL).netloc:
        return []
    static_root = Path(settings.STATIC_ROOT)
    if not static_root.is_dir():
        # granian refuses to start with a mount that does not exist.
        warnings.warn(f"{static_root} is missing; run collectstatic.", RuntimeWarning, stacklevel=2)
        return []
    return [
        "--static-path-route",
        settings.STATIC_URL.rstrip("/"),
        "--static-path-mount",
        str(static_root),
        "--static-path-expires",
        str(STATIC_EXPIRES),
    ]


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
    if not settings.DEBUG:
        argv += _static_files_options()
    # The environment, not an option: a granian option would override GRANIAN_WORKERS_KILL_TIMEOUT.
    kill_timeout = RELOAD_KILL_TIMEOUT if reload else KILL_TIMEOUT
    os.environ.setdefault("GRANIAN_WORKERS_KILL_TIMEOUT", kill_timeout)
    if reload:
        argv += ["--reload", "--reload-paths", str(base_dir / PACKAGE)]
        # DEBUG reloads templates without a restart, and browser-reload refreshes the page.
        argv += ["--reload-ignore-dirs", "templates", "--reload-ignore-dirs", "locale"]
    # execv replaces the process, so unflushed output would be lost.
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, argv)
