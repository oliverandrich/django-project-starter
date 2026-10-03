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
mise run runserver       # dev server with the Tailwind watcher
mise run migrate
mise run makemigrations
mise run shell           # shell_plus
mise run manage <args>   # any other manage.py command
mise run lint            # pre-commit: ruff, ty, django-upgrade, djade
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

SQLite is the default database, tuned by dj-lite.
`DATABASE_URL` switches to PostgreSQL or MySQL.

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

## Tests

Tests use Django's test framework with django-test-plus and model-bakery.
The test runner in `<package>/test_runner.py` adds rich output.
It also swaps the manifest static storage for a plain one, so tests need no `collectstatic`.
Write a failing test before a fix or a feature.

## Production

WhiteNoise serves static files with hashed names from the manifest.
The Docker image runs Granian on port 8000 and migrates on start.
`SECRET_KEY` and `ALLOWED_HOSTS` must be set outside `DEBUG`.
