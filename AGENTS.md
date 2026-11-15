# AGENTS.md

Conventions for this Django project. They apply to people and coding agents alike.

## Layout

The project uses the [single folder layout](https://noumenal.es/notes/django/single-folder-layout/).
Models, views, admin, templates and commands live in the project package next to `settings.py`.
The project package is the directory named after the project.
It is itself the one Django app in `INSTALLED_APPS`.

Do not create apps by default.
Run `mise run manage startapp <name>` only when a part needs its own models and boundary.
A reusable app or a clearly separate domain justifies one. File size alone does not.

- `<package>/`: settings, URLs, views, models, admin, templates, locale, management commands
- `tests/`: the test suite
- `assets/`: static source files; `assets/css/tailwind.css` is generated
- `docker/`: Dockerfile and entrypoint for production
- `logs/`: log files of management commands, ignored by git

## Commands

Run everything through mise. It pins Python and uv, and loads `.env`.

```bash
mise run bootstrap       # first setup: .env, dependencies, CSS, git, pre-commit hook
mise run upgrade         # upgrade all dependencies
mise run debugserver     # runserver, worker and scheduler together; Ctrl-C stops all
mise run runserver       # dev server with the Tailwind watcher; use it for breakpoint()
mise run migrate
mise run makemigrations
mise run shell           # shell_plus
mise run worker          # run queued tasks (database task backend only)
mise run scheduler       # enqueue @cron tasks on their schedule
mise run manage <args>   # any other manage.py command
mise run lint            # pre-commit: ruff, basedpyright, django-upgrade, djade
mise run test            # test suite with coverage
```

## Done means checked

Run `mise run lint` and `mise run test` before calling a change done.
Both run in CI on every pull request.
CI also builds the Docker image.

## Configuration

Settings read the environment through environs, following the 12-factor approach.
`.env` holds local values and is ignored by git.
Add new settings as environment variables with a development default.
Do not add a second settings module per environment.

PostgreSQL is the only supported database, through psycopg 3.
`DATABASE_URL` defaults to `postgres:///<package>` over the local Unix socket.
`mise run manage createdb` creates that database; `mise run bootstrap` calls it.
Tests need a running PostgreSQL server and the CREATEDB privilege.

## Frontend

Pages are rendered on the server.
htmx adds interactivity; there is no JavaScript build step and no SPA framework.
django-htmx serves htmx and provides `request.htmx`.
Tailwind CSS with daisyUI comes from django-tailwind-cli, which needs no Node.js.
`base.html` enables `hx-boost` for the whole page.

The template builtins include `i18n`, `static` and `heroicons`.
Templates use them without `{% load %}`.

## Management commands

Write commands as django-click functions with `@command()` from `<package>/management/base.py`.
`@command()` adds a rotating log file in `logs/`, the system checks and `--skip-checks`.
`@pass_logger` passes the command's logger in as `logger`.

```python
import djclick as click

from <package>.management.base import command, pass_logger


@command()
@click.argument("source")
@pass_logger
def main(logger, source):
    logger.info("importing from %s", source)
```

## Tasks

Tasks use Django's tasks framework, `django.tasks`.
Define them in `<package>/tasks.py` with `@task`.
The default backend, `django_tasks_db.DatabaseBackend`, stores tasks for `mise run worker`.
`TASKS_BACKEND=django.tasks.backends.immediate.ImmediateBackend` runs a task inside `enqueue()`.

django-crontask schedules recurring tasks.
Put `@cron("<crontab>")` above `@task`.
The day-of-week field takes names such as `Mon`, not numbers.
`mise run scheduler` enqueues each task on its schedule, in `TIME_ZONE`.
`prune_task_results` deletes finished results older than 14 days at 03:00.

`<package>/scheduler_lock.py` lets one scheduler run per database through an advisory lock.
A second scheduler exits after 15 seconds.
A transaction-pooling PgBouncer breaks the lock.

## Tests

Tests use Django's test framework with django-test-plus and model-bakery.
The test runner in `<package>/test_runner.py` adds rich output.
It also swaps the manifest static storage for a plain one, so tests need no `collectstatic`.
It sets the default task backend to `ImmediateBackend`, so enqueued tasks run inside the test.
Write a failing test before a fix or a feature.

## Production

WhiteNoise serves static files with hashed names from the manifest.
The Docker image runs Granian on port 8000 and migrates on start.
The arguments `worker` and `scheduler` start the task worker and the scheduler from the same image.
Only the web process migrates, so start the others after it.
`SECRET_KEY` and `ALLOWED_HOSTS` must be set outside `DEBUG`.
