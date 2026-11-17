# django-project-starter

> Django startproject template for Django projects with batteries included and nice tooling.

I took the inspiration from Jeff Triplett's [django-startproject](https://github.com/jefftriplett/django-startproject) and created my own starter for a fresh django project. It includes the batteries I use regularly. 🤷‍♂️

The template is also inspired by Carlton Gibson's Post [The Single Folder Django Project Layout](https://noumenal.es/notes/django/single-folder-layout/). It uses the single folder layout as a start as I always run in the same situation Carlton describes in his post. If you have to split the project into several apps, you can always call `python manage.py startapp` later on.

The starter runs on PostgreSQL only. The last SQLite version is tagged `sqlite-final`.

## Features

- Python 3.14
- Django 6.1
- django-htmx
- django-tailwind-cli
- django-click
- environs\[django\]
- heroicons
- [granian](https://github.com/emmett-framework/granian) serving ASGI, in development and in the Docker image
- PostgreSQL through psycopg 3; `mise run bootstrap` creates the database
- Django's database cache in an UNLOGGED PostgreSQL table, created by `migrate`
- [Argon2 password hashing](https://docs.djangoproject.com/en/6.1/topics/auth/passwords/)
- uses the [single folder Django project layout](https://noumenal.es/notes/django/single-folder-layout/)
- [adds some standard templatetags to the builtins](https://adamj.eu/tech/2023/09/15/django-move-template-tag-library-builtins/)
- htmx 4 with its hx-sse extension, vendored in `assets/vendor/htmx` and updated with `mise run update-htmx <version>`.
- Live updates through [django-pg-sse](https://github.com/oliverandrich/django-pg-sse): `broadcast()` pushes HTML to an SSE endpoint over PostgreSQL LISTEN/NOTIFY, with replay after a reconnect.
- Background tasks with `django.tasks`: [django-tasks-db](https://github.com/RealOrangeOne/django-tasks-db) queues them in PostgreSQL, [django-crontask](https://github.com/codingjoe/django-crontask) schedules recurring ones. An advisory lock keeps a second scheduler from running.
- A `@command()` decorator for django-click management commands. They log to a rotating logfile, and to the console in an interactive shell.

### Development tools

- django-types + basedpyright
- django-browser-reload
- model-bakery & faker for smarter testing fixtures
- pre-commit setup inspired by [Boost your Django DX](https://adamchainz.gumroad.com/l/byddx)
- sane ruff configuration
- [uv](https://docs.astral.sh/uv/) for dependency management
- [mise](https://mise.jdx.dev) for the toolchain and for project tasks
- GitHub Actions CI for lint, tests and the Docker build
- Dependabot for uv, pre-commit, GitHub Actions and Docker
- `AGENTS.md` with the project's conventions, imported by `CLAUDE.md`

## Install

```shell
# Pull the template from GitHub
$ uv run --with=django django-admin startproject \
    --extension=ini,py,toml,sh \
    --exclude=template_tests \
    --template=https://github.com/oliverandrich/django-project-starter/archive/refs/heads/main.zip \
    example_project

$ cd example_project
$ mise trust          # once, so mise reads mise.toml
$ mise run bootstrap  # .env, dependencies, database, first CSS build, git, pre-commit hook
$ mise run debugserver
```

`--exclude` is not optional, and its effect is indirect. Django drops **every** directory whose
name starts with a dot unless the flag is passed *at all* — so without it `.mise/` never arrives
and the generated project carries a `mise.toml` pointing at file tasks that were never copied.
Passing it switches Django to the explicit list, and `template_tests` is what belongs on that
list: the published archive is `git archive` output, so it holds tracked files and nothing else.

Generating from a local checkout instead of the URL is different — a virtualenv and tool caches
are sitting on disk there, and git-ignored files are not filtered out by anything. Add
`--exclude=.venv --exclude=.idea --exclude=.claude --exclude=.pytest_cache --exclude=.ruff_cache`
in that case, or generate from the URL and avoid the question.

## Usage

```shell
# Upgrade/install all dependencies defined in pyproject.toml
mise run upgrade

# Run database migrations
mise run migrate

# Create database migrations
mise run makemigrations

# Start granian (ASGI), Tailwind, the task worker and the scheduler together; Ctrl-C stops all
mise run debugserver

# Start the WSGI development server with Tailwind, for breakpoint()
mise run runserver

# Start the interactive django shell
mise run shell

# Run queued tasks (needs TASKS_BACKEND=django_tasks_db.DatabaseBackend)
mise run worker

# Enqueue @cron tasks on their schedule
mise run scheduler

# Start manage.py for all cases not covered by other commands
mise run manage ...

# Run pre-commit rules on all files
mise run lint

# Run the test suite with coverage
mise run test
```

`mise run worker` exits at once when `TASKS_BACKEND` selects a backend other than django_tasks_db's.
The scheduler does not reload on code changes. Restart `debugserver` after changing a schedule.
`debugserver` gives its tasks no stdin. Use `mise run runserver` to stop at a `breakpoint()`.

## Environment Variables for Docker and your .env file

Or when run as a [12-Factor application](https://12factor.net).

| Environment Variable         | Default                                           | Location        |
| ---------------------------- | ------------------------------------------------- | --------------- |
| ALLOWED_HOSTS                | []                                                | settings.py     |
| CACHE_URL                    | "db://django_cache?max_entries=10000"             | settings.py     |
| CSRF_TRUSTED_ORIGINS         | []                                                | settings.py     |
| DATABASE_POOL                | True                                              | settings.py     |
| DATABASE_POOL_MAX_SIZE       | 10                                                | settings.py     |
| DATABASE_POOL_MIN_SIZE       | 1                                                 | settings.py     |
| DATABASE_URL                 | "postgres:///<project>" (local socket)            | settings.py     |
| DEBUG                        | False                                             | settings.py     |
| EMAIL_URL                    | "console:"                                        | settings.py     |
| EVENTS_RETENTION_HOURS       | 24                                                | settings.py     |
| INTERNAL_IPS                 | []                                                | settings.py     |
| LANGUAGE_CODE                | "en"                                              | settings.py     |
| SECRET_KEY                   |                                                   | settings.py     |
| TASKS_BACKEND                | "django_tasks_db.DatabaseBackend"                 | settings.py     |
| TIME_ZONE                    | "UTC"                                             | settings.py     |
| GRANIAN_HOST                 | "0.0.0.0" in the image, "127.0.0.1" otherwise     | granian         |
| GRANIAN_WORKERS              | 1                                                 | granian         |
| GRANIAN_RUNTIME_THREADS      | 1                                                 | granian         |
| GRANIAN_BACKPRESSURE         | 8192                                              | manage.py serve |
| GRANIAN_WORKERS_KILL_TIMEOUT | 5, or 1 with `--reload`                           | manage.py serve |
| GRANIAN_*                    | see <https://github.com/emmett-framework/granian> | granian         |

## Docker and docker-compose

The `docker/Dockerfile` uses a multi stage process to embrace caching for building the container images.

The image starts the web server by default. Pass `worker` or `scheduler` as the command to start
the task worker or the cron scheduler from the same image. Only the web server runs migrations.
Every process needs `DATABASE_URL` pointing at the PostgreSQL server.

### Behind Caddy

The image expects a reverse proxy in front. granian serves static files from `STATIC_ROOT` with
a one-year cache and no compression; Caddy compresses them and the pages.

```caddyfile
example.com {
    encode zstd gzip
    reverse_proxy web:8000
}
```

`collectstatic` keeps only hashed file names, so the long cache never serves a stale file.
Caddy 2 passes server-sent events through without buffering, also with `encode` enabled.

## License

This software is licensed under [MIT license](./LICENSE).
