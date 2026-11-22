# django-project-starter

> Django startproject template for Django projects with batteries included and nice tooling.

I took the inspiration from Jeff Triplett's [django-startproject](https://github.com/jefftriplett/django-startproject) and created my own starter for a fresh django project. It includes the batteries I use regularly. 🤷‍♂️

The template is also inspired by Carlton Gibson's Post [The Single Folder Django Project Layout](https://noumenal.es/notes/django/single-folder-layout/). It uses the single folder layout as a start as I always run in the same situation Carlton describes in his post. If you have to split the project into several apps, you can always call `python manage.py startapp` later on.

The starter runs on PostgreSQL by default. SQLite through dj-lite is an option for a single server.

## Features

- Python 3.14
- Django 6.1
- django-htmx
- django-tailwind-cli
- django-click
- environs\[django\]
- heroicons
- [granian](https://github.com/emmett-framework/granian) serving ASGI, in development and in the Docker image
- PostgreSQL through psycopg 3, or SQLite through [dj-lite](https://github.com/adamghill/dj-lite); `mise run bootstrap` creates and migrates the database
- Django's database cache, created by `migrate`; on PostgreSQL in an UNLOGGED table
- Email through Django 6.1's `MAILERS`, configured by `EMAIL_URL` with [dj-email-url](https://github.com/migonzalvar/dj-email-url)
- [Argon2 password hashing](https://docs.djangoproject.com/en/6.1/topics/auth/passwords/)
- uses the [single folder Django project layout](https://noumenal.es/notes/django/single-folder-layout/)
- [adds some standard templatetags to the builtins](https://adamj.eu/tech/2023/09/15/django-move-template-tag-library-builtins/)
- htmx 4 with its hx-sse extension, vendored in `assets/vendor/htmx` and updated with `mise run update-htmx <version>`.
- A project `User` model as `AUTH_USER_MODEL` from the first migration.
- Optional login methods, any combination: password, Microsoft Entra ID through [django-auth-adfs](https://github.com/snok/django-auth-adfs), and single-use links by email through [django-sesame](https://github.com/aaugustin/django-sesame).
- Optional: live updates through [django-pg-sse](https://github.com/oliverandrich/django-pg-sse): `broadcast()` pushes HTML to an SSE endpoint over PostgreSQL LISTEN/NOTIFY, with replay after a reconnect.
- Optional: background tasks with `django.tasks`: [django-tasks-db](https://github.com/RealOrangeOne/django-tasks-db) queues them in PostgreSQL, [django-crontask](https://github.com/codingjoe/django-crontask) schedules recurring ones. An advisory lock keeps a second scheduler from running. A cron task marks tasks as failed that run longer than `TASKS_STALE_AFTER_MINUTES`.
- JSON logs through [django-structlog](https://github.com/jrobichaud/django-structlog), with a request id and without an access log, query strings or client addresses.
- `/health` and `/health/ready` for container health checks, answered before `ALLOWED_HOSTS`.
- A strict Content Security Policy through Django 6's `SECURE_CSP`: scripts and styles only from the site's origin, no inline code.
- A `@command()` decorator for django-click management commands. They log to a rotating logfile, and to the console in an interactive shell.

### Development tools

- django-types + basedpyright
- django-browser-reload
- model-bakery & faker for smarter testing fixtures
- Playwright browser tests in Chromium, run by `mise run test-browser`
- pre-commit setup inspired by [Boost your Django DX](https://adamchainz.gumroad.com/l/byddx)
- sane ruff configuration
- [uv](https://docs.astral.sh/uv/) for dependency management
- [mise](https://mise.jdx.dev) for the toolchain and for project tasks
- GitHub Actions CI for lint, tests and, optionally, the Docker build
- Dependabot for uv, pre-commit, GitHub Actions and, with the image, Docker
- `AGENTS.md` with the project's conventions, imported by `CLAUDE.md`

## Install

```shell
# Answer the questions: the package name, and whether to include live updates
$ uvx copier copy --trust gh:oliverandrich/django-project-starter example_project

$ cd example_project
$ mise trust          # once, so mise reads mise.toml
$ mise run bootstrap  # .env, dependencies, database, first CSS build, git, pre-commit hook
$ mise run debugserver
```

`--data database=sqlite` uses SQLite through dj-lite instead of PostgreSQL, for a single server.
It leaves out live updates, which need PostgreSQL's LISTEN/NOTIFY.
`--data live_updates=false` leaves out django-pg-sse, its settings, URL, task and tests.
`--data background_tasks=false` leaves out django-tasks-db, django-crontask, the worker and the scheduler.
`django.tasks` then runs each task inside `enqueue()`, Django's default.
`--data 'login=["microsoft", "magic_link"]'` picks login methods; the default `[]` keeps only the admin login.
`--data daisy_ui=true` turns on daisyUI; the login pages use plain Tailwind either way.
`--data docker=false` leaves out the Dockerfile, the entrypoint and the Docker job in CI.
`--data license=AGPL-3.0-or-later` picks the AGPL; the default is `MIT`.
`--data license=proprietary` writes no LICENSE file and marks `pyproject.toml` private.
`--data author="Jane Doe"` names the copyright holder; `copyright_year` defaults to the current year.

## Update

`.copier-answers.yml` records the template version and the answers.
`uvx copier update` merges later changes of the template into the project.
Run it on a clean working tree; conflicts show up as `.rej` files or conflict markers.
It leaves the project's `README.md` alone.
On its next update, a project generated before the license question defaults to `MIT`.
Copier then prompts for `author`; a run with `--defaults` needs `--data author=...`.
The README's license section is written once at `copier copy` and not updated afterwards.
`daisy_ui` defaults to `false`; a project that uses daisyUI classes answers `daisy_ui=true` on update.

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

# Run the browser tests in Chromium (once: uv run python -m playwright install chromium)
mise run test-browser
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
| DATABASE_POOL                | True; PostgreSQL only                             | settings.py     |
| DATABASE_POOL_MAX_SIZE       | 10; PostgreSQL only                               | settings.py     |
| DATABASE_POOL_MIN_SIZE       | 1; PostgreSQL only                                | settings.py     |
| DATABASE_URL                 | "postgres:///<project>"; PostgreSQL only          | settings.py     |
| DEBUG                        | False                                             | settings.py     |
| EMAIL_URL                    | "console:"                                        | settings.py     |
| EVENTS_RETENTION_HOURS       | 24                                                | settings.py     |
| INTERNAL_IPS                 | []                                                | settings.py     |
| LANGUAGE_CODE                | "en"                                              | settings.py     |
| SECRET_KEY                   |                                                   | settings.py     |
| SECURE_HSTS_SECONDS          | 0                                                 | settings.py     |
| SITE_URL                     | "http://localhost:8000" in DEBUG; magic_link only | settings.py     |
| SQLITE_PATH                  | "db.sqlite3" in the project; SQLite only          | settings.py     |
| TASKS_BACKEND                | "django_tasks_db.DatabaseBackend"                 | settings.py     |
| TASKS_STALE_AFTER_MINUTES    | 60                                                | settings.py     |
| TIME_ZONE                    | "UTC"                                             | settings.py     |
| GRANIAN_HOST                 | "0.0.0.0" in the image, "127.0.0.1" otherwise     | granian         |
| GRANIAN_WORKERS              | 1                                                 | granian         |
| GRANIAN_RUNTIME_THREADS      | 1                                                 | granian         |
| GRANIAN_BACKPRESSURE         | 8192                                              | manage.py serve |
| GRANIAN_WORKERS_KILL_TIMEOUT | 5, or 1 with `--reload`                           | manage.py serve |
| GRANIAN_*                    | see <https://github.com/emmett-framework/granian> | granian         |

## Docker and docker-compose

This section applies unless the project was generated with `docker=false`.
The `docker/Dockerfile` uses a multi stage process to embrace caching for building the container images.

The image starts the web server by default. Pass `worker` or `scheduler` as the command to start
the task worker or the cron scheduler from the same image. Only the web server runs migrations.
Every process needs `DATABASE_URL` pointing at the PostgreSQL server.
With SQLite, every container mounts the same named volume at `/data` instead.

`docker/compose.yaml` runs the image with the database and every process the project needs:
`docker compose -f docker/compose.yaml up --build --wait`. Its settings and secrets go into
`docker/.env`; the file's header lists the required ones. A TLS proxy forwards to `127.0.0.1:8000`.
CI builds the image and starts the example through `docker/smoke-test.sh`.
A tag such as `v1.2.0` publishes the image to the GitHub Container Registry as `1.2.0` and `1.2`.

The worker finishes its current task on the first SIGTERM, then exits.
Docker sends SIGKILL after 10 seconds, which leaves a longer task `RUNNING`.
Set the worker's `stop_grace_period` in Compose above the runtime of the longest task.
`docker run` takes `--stop-timeout` for the same purpose.
`fail_stale_tasks` marks a task `FAILED` that stays `RUNNING` beyond `TASKS_STALE_AFTER_MINUTES`.

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
