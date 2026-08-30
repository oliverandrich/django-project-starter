"""A management command base that logs to a rotating logfile and, interactively, the console.

Built on django-click rather than Django's own `BaseCommand`, so commands are written as click
functions:

    # {{ project_name }}/management/commands/import_things.py
    import djclick as click

    from {{ project_name }}.management.base import command, pass_logger


    @command()
    @click.argument("source")
    @pass_logger
    def main(logger, source):
        logger.info("importing from %s", source)

There is no `TyperCommand` to subclass. `BaseRegistrator.__call__` passes `cls=self.cls` into
`click.command` alongside `**self.kwargs`, so a `cls=` at the decorator call site collides with it
(`TypeError: got multiple values for keyword argument 'cls'`); the command class is overridable
only by subclassing the registrator, which is what `command` below does. `pass_logger` follows
django-click's own `pass_verbosity`.

Two things Django's `BaseCommand` does and django-click does not are restored here: the system
checks, and the `--skip-checks` option that turns them off.
"""

import functools
import logging
import sys
from collections.abc import Callable
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import click
import djclick
from django.conf import settings
from django.core.management.base import BaseCommand as DjangoBaseCommand
from djclick.adapter import CommandRegistrator, DjangoCommandMixin, register_on_context
from environs import Env

DEFAULT_MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_LOG_BACKUP_COUNT = 10

# Marks the handlers this module installed. Running a command twice in one process must not stack
# up duplicate handlers, but clearing the logger outright would throw away a `settings.LOGGING`
# entry the project configured for a logger of the same name.
_OWN_HANDLER = "_managed_by_base_py"


def _is_a_tty() -> bool:
    """Whether stdout is a terminal, for every stdout the test runners substitute.

    `sys.stdout.isatty()` rather than `os.isatty(sys.stdout.fileno())`: pytest's capture replaces
    stdout with an object that has no file descriptor, and `fileno()` raises there. The
    `callable` guard covers `sys.stdout is None`, which happens under pythonw and some embedded
    interpreters. A *closed* stdout still raises, and deliberately so — that is a broken program,
    not a capture layer.
    """
    return callable(getattr(sys.stdout, "isatty", None)) and sys.stdout.isatty()


def _build_logger(name: str) -> Logger:
    """A logger writing to logs/<name>.log, plus the console when there is one."""
    logger = logging.getLogger(name)
    for handler in [h for h in logger.handlers if getattr(h, _OWN_HANDLER, False)]:
        logger.removeHandler(handler)
        handler.close()
    logger.propagate = False

    formatter = logging.Formatter("%(levelname)-8s %(asctime)s [%(process)-8d] %(message)s")

    env = Env()
    env.read_env()
    logfile = Path(settings.BASE_DIR) / "logs" / f"{name}.log"
    # A Docker build or a tarball can arrive without it; RotatingFileHandler would otherwise
    # fail with a FileNotFoundError traceback before the command runs.
    logfile.parent.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            logfile,
            maxBytes=env.int(
                f"{name.upper()}_MAX_LOG_FILE_SIZE", default=DEFAULT_MAX_LOG_FILE_SIZE
            ),
            backupCount=env.int(
                f"{name.upper()}_MAX_LOG_BACKUP_COUNT", default=DEFAULT_MAX_LOG_BACKUP_COUNT
            ),
            encoding="utf-8",
        )
    ]
    if _is_a_tty():
        handlers.append(logging.StreamHandler())

    for handler in handlers:
        handler.setFormatter(formatter)
        setattr(handler, _OWN_HANDLER, True)
        logger.addHandler(handler)

    return logger


def _as_argv(param: click.Parameter, value: Any) -> list[str]:
    """One `call_command` keyword spelled back as argv, or a refusal that says why.

    The shapes below cannot survive the round trip, and each of them used to produce silently
    wrong argv: a `multiple=True` option became one option holding the `repr` of the list, a
    `count=True` option turned its value into a stray positional, and a hidden `click.Argument`
    emitted its own name as a positional and shifted every real one. Raising is the point —
    these are programming errors in a command's own signature, and a command that cannot be
    reached by keyword should say so rather than run with different values than it was given.
    """
    if isinstance(param, click.Argument):
        raise TypeError(f"{param.name!r} is an argument — pass it positionally to call_command.")
    if param.multiple or param.nargs != 1 or getattr(param, "count", False):
        raise TypeError(f"{param.name!r} cannot be passed to call_command as a keyword.")

    if getattr(param, "is_flag", False):
        if value:
            return [param.opts[0]]
        if param.secondary_opts:
            return [param.secondary_opts[0]]
        if param.default:
            raise TypeError(
                f"{param.name!r} is a flag that defaults to on and has no --no- form, "
                "so call_command cannot turn it off."
            )
        return []  # default-off flag, and absence already means off
    return [param.opts[0], str(value)]


class _Prepared(click.Command):
    """Runs the system checks and builds the logger, just before the command function runs.

    A plain `click.Command`, and that placement is the point: `LoggingCommand` puts
    django-click's `DjangoCommandMixin` *above* this in the MRO, so a `SystemCheckError` raised
    here is caught by that mixin and reported as one red line and exit 1 — the way Django
    reports it. Raised from `LoggingCommand.invoke` instead, it would escape the mixin's
    try-block and reach the terminal as a traceback.
    """

    logger: Logger

    def invoke(self, ctx: click.Context) -> Any:
        if not getattr(ctx, "skip_checks", False):
            # A throwaway Django command purely for its `check()`: a django-click command is not
            # a Django command and has no checks of its own.
            DjangoBaseCommand().check()

        # `self.name` is the module name django-click derived, which is the command name Django
        # knows. The previous implementation read `sys.argv[1]`, which under `call_command` is
        # whatever the test runner was invoked with.
        self.logger = _build_logger(self.name or "command")
        self.logger.setLevel(logging.DEBUG if getattr(ctx, "verbosity", 1) > 1 else logging.INFO)
        ctx.logger = self.logger  # pyright: ignore[reportAttributeAccessIssue]

        return super().invoke(ctx)


class LoggingCommand(DjangoCommandMixin, _Prepared):
    """django-click's `CommandAdapter` with the checks and the logger folded in.

    Spelled out rather than subclassing `CommandAdapter`, because the order matters — see
    `_Prepared`.
    """

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """The `call_command` entry point. Django's semantics, which django-click does not keep.

        `DjangoCommandMixin.execute` builds the click context and *then* does
        `ctx.params.update(...)`, so a keyword never reaches its option's parse callback. For the
        options declared with `expose_value=False` — `--verbosity`, `--settings`, `--traceback`,
        `--color`, `--skip-checks` — that is not merely inert: click hands the leftover key to the
        command function, and `call_command("thing", verbosity=0)`, which every second Django test
        does, dies with `TypeError: got an unexpected keyword argument 'verbosity'`.

        Spelling them back as argv and letting click parse them normally fixes all of it at once.
        """
        # Django skips the system checks under call_command unless the caller says otherwise, and
        # the command line is the other entry point, so this default belongs here rather than in a
        # flag threaded through invoke(). It also keeps a nested call_command from re-running the
        # checks the outer command already ran.
        kwargs["skip_checks"] = kwargs.pop("skip_checks", True)
        # Django lets a CommandError out of call_command; django-click turns it into `ctx.exit(1)`
        # unless ctx.traceback is set. Default it on, so `pytest.raises(CommandError)` works.
        # Passing traceback=False restores django-click's swallow, and then the `ctx.exit(1)`
        # surfaces as `click.exceptions.Exit` — neither a CommandError nor a SystemExit. Django
        # has no such mode; there is no reason to ask for it.
        kwargs.setdefault("traceback", True)

        # Django advertises every spelling of an option as a valid keyword — see
        # `DjangoCommandMixin.stealth_options` — so `call_command(cmd, v=0)` is legal and means
        # verbosity. Fold those onto the parameter names before matching.
        for param in self.params:
            for opt in param.opts:
                alias = opt.lstrip("-").replace("-", "_")
                if alias != param.name and alias in kwargs:
                    kwargs[param.name] = kwargs.pop(alias)

        options: list[str] = []
        for param in self.params:
            if param.expose_value or not param.name or param.name not in kwargs:
                continue
            value = kwargs.pop(param.name)
            if value is not None:
                options.extend(_as_argv(param, value))

        # Prepended, not appended: a command with `--` or with interspersed arguments turned off
        # stops parsing at the first positional, and these would never be seen after it.
        return super().execute(*options, *args, **kwargs)


class command(CommandRegistrator):  # noqa: N801 - used as a decorator, named like one
    """`@command()` — django-click's `@click.command()` plus logging and system checks."""

    cls = LoggingCommand
    common_options = [
        *CommandRegistrator.common_options,
        djclick.option(
            "--skip-checks",
            is_flag=True,
            expose_value=False,
            callback=register_on_context,
            help="Skip system checks.",
        ),
    ]


def pass_logger(f: Callable[..., Any]) -> Callable[..., Any]:
    """Pass the command's logger in as a keyword argument, like django-click's `pass_verbosity`."""

    def new_func(*args: Any, **kwargs: Any) -> Any:
        ctx = click.get_current_context()
        if not hasattr(ctx, "logger"):
            raise RuntimeError(
                "@pass_logger needs the @command() from this module; a plain djclick.command "
                "never sets up a logger."
            )
        kwargs["logger"] = ctx.logger  # pyright: ignore[reportAttributeAccessIssue]
        return f(*args, **kwargs)

    return functools.update_wrapper(new_func, f)
