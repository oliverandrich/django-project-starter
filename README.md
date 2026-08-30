# django-project-starter

> Django startproject template for Django projects with batteries included and nice tooling.

I took the inspiration from Jeff Triplett's [django-startproject](https://github.com/jefftriplett/django-startproject) and created my own starter for a fresh django project. It includes the batteries I use regularly. 🤷‍♂️

The template is also inspired by Carlton Gibson's Post [The Single Folder Django Project Layout](https://noumenal.es/notes/django/single-folder-layout/). It uses the single folder layout as a start as I always run in the same situation Carlton describes in his post. If you have to split the project into several apps, you can always call `python manage.py startapp` later on.

Out of the box SQLite is configured, but you can easily activate MySQL or Postgres support.

## Features

- Python 3.13
- Django 6.1
- django-htmx
- django-tailwind-cli
- django-click
- environs\[django\]
- heroicons
- whitenoise
- Production-ready SQLite settings via [dj-lite](https://github.com/adamghill/dj-lite)
- [Argon2 password hashing](https://docs.djangoproject.com/en/6.1/topics/auth/passwords/)
- uses the [single folder Django project layout](https://noumenal.es/notes/django/single-folder-layout/)
- [adds some standard templatetags to the builtins](https://adamj.eu/tech/2023/09/15/django-move-template-tag-library-builtins/)
- A local install of alpine.js and htmx.
- BaseCommand class for writing management commands that log to a rotating logfile and the console if run in an interactive shell.

### Development tools

- django-types + pyright
- django-browser-reload
- model-bakery & faker for smarter testing fixtures
- pre-commit setup inspired by [Boost your Django DX](https://adamchainz.gumroad.com/l/byddx)
- sane ruff configuration
- [uv](https://docs.astral.sh/uv/) for dependency management
- [mise](https://mise.jdx.dev) for the toolchain and for project tasks

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
$ mise run bootstrap  # .env, dependencies, first CSS build, git, pre-commit hook
$ mise run runserver
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

# Start debugserver
mise run runserver
# or
mise run debugserver

# Start the interactive django shell
mise run shell

# Start manage.py for all cases not covered by other commands
mise run manage ...

# Run pre-commit rules on all files
mise run lint

# Run the test suite with coverage
mise run test
```

`mise run dev` opens a three-pane tmux session (agent, `debugserver`, a free shell); `mise run
dev stop` shuts it down again. It runs on its own tmux server, named after the project
directory, so it is reachable from a plain shell with `tmux -L <project> attach`.

## Environemt Variables for Docker and your .env file

Or when run as a [12-Factor application](https://12factor.net).

| Environment Variable | Default                                           | Location      |
| -------------------- | ------------------------------------------------- | ------------- |
| ALLOWED_HOSTS        | []                                                | settings.py   |
| CACHE_URL            | "locmem://"                                       | settings.py   |
| CSRF_TRUSTED_ORIGINS | []                                                | settings.py   |
| DATABASE_URL         | SQLite via dj-lite                                | settings.py   |
| DEBUG                | False                                             | settings.py   |
| EMAIL_URL            | "console:"                                        | settings.py   |
| INTERNAL_IPS         | []                                                | settings.py   |
| LANGUAGE_CODE        | "EN"                                              | settings.py   |
| SECRET_KEY           |                                                   | settings.py   |
| TAILWIND_CLI_PATH    | "~/.local/bin"                                    | settings.py   |
| TIME_ZONE            | "UTC"                                             | settings.py   |
| GRANIAN_WORKERS      | 1                                                 | entrypoint.sh |
| GRANIAN_THREADS      | 1                                                 | entrypoint.sh |
| GRANIAN_*            | see <https://github.com/emmett-framework/granian> | entrypoint.sh |

## Docker and docker-compose

The `docker/Dockerfile` uses a multi stage process to embrace caching for building the container images.

## License

This software is licensed under [MIT license](./LICENSE).
