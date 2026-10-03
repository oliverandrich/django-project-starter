# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Django project template** for use with `django-admin startproject`. It provides a batteries-included starter template with modern tooling and best practices. When using this template, `{{ project_name }}` placeholders will be replaced with the actual project name.

## Common Development Commands

### Project Setup
```bash
# Bootstrap new project (first time only; `mise trust` once before this)
mise run bootstrap

# Install/upgrade all dependencies
mise run upgrade
```

### Development Server
```bash
# Start development server with Tailwind CSS hot-reload
mise run runserver
# or
mise run debugserver
```

### Database Operations
```bash
# Run migrations
mise run migrate

# Create new migrations
mise run makemigrations
```

### Testing and Quality
```bash
# Run the test suite with coverage
mise run test

# Run all pre-commit checks (linting, formatting, type checking)
mise run lint

# Run specific linters if needed
uv run ruff check .
uv run ruff format .
uv run ty check
```

### Interactive Shell
```bash
# Start Django shell with shell_plus
mise run shell
```

### Other Django Commands
```bash
# For any other manage.py commands
mise run manage <command>
```

## Project Architecture

This Django project uses a **single folder layout** where the main application logic resides directly in the `project_name` directory rather than splitting into multiple apps initially. This approach simplifies the initial development and can be expanded to multiple apps later using `python manage.py startapp`.

### Key Directories

- **`project_name/`**: Main Django application directory (will be renamed to actual project name) containing:
  - `settings.py`: Configuration using environment variables via `environs[django]`
  - `urls.py`: URL routing
  - `views.py`: View logic
  - `models.py`: Database models
  - `admin.py`: Django admin configuration
  - `templates/`: HTML templates with base template structure
  - `management/`: Custom management commands with BaseCommand for consistent logging
  - `locale/`: Translation files for i18n (English and German)

- **`tests/`**: Test suite using Django's test framework with django-test-plus and django-rich test runner
- **`template_tests/`**: Tests for the template itself (`mise run test-template`). Excluded from generation — never ships into a project
- **`assets/`**: Static assets (CSS, JS) served by WhiteNoise
- **`logs/`**: Log files from management commands (gitignored)
- **`docker/`**: Docker configuration with Granian ASGI server

### Technology Stack

- **Frontend**: HTMX + Tailwind CSS (via django-tailwind-cli with DaisyUI)
- **Backend**: Django 6.1 with django-htmx, django-click for CLI commands
- **Database**: SQLite with optimized settings (can switch to PostgreSQL/MySQL via DATABASE_URL)
- **Security**: Argon2 password hashing, environment-based configuration
- **Development Tools**:
  - `uv` for dependency management
  - `mise` for the toolchain and task automation
  - Pre-commit hooks with ruff, ty, django-upgrade, djade
  - Type checking with ty and django-types

### Configuration

The project uses environment variables for configuration with sensible defaults for development:
- Create a `.env` file for local development (auto-created by `mise run bootstrap`)
- Key settings: `DEBUG`, `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`
- Email configuration via `EMAIL_URL`
- Cache configuration via `CACHE_URL`

### Custom Features

1. **BaseCommand**: All management commands should inherit from `project_name.management.base.BaseCommand` for automatic rotating log file handling
2. **Template Builtins**: Common templatetags (i18n, static, heroicons) are pre-loaded
3. **Optimized SQLite**: Includes performance optimizations for SQLite when used
4. **Static File Serving**: WhiteNoise configured for production-ready static file serving

### Working on the template itself

This repository is a template, not a runnable project, and two things follow from that:

- **`uv sync` does not work here.** `pyproject.toml` says `name = "{{ project_name }}"`, which uv
  rejects as a package name, so the repository has no `.venv` and never will. `mise run lint`
  therefore fails at the ty hook, which runs through `uv run`. Run
  `SKIP=ty mise run lint` here; ty belongs to the generated project, where
  `mise run lint` passes in full.
- **`mise run test-template` is the suite that applies here**, and it runs on `uvx pytest` for
  exactly the reason above — `uv run` would parse `pyproject.toml` and fail. Its task file lives
  in `template_tests/tasks/`, wired in through `[task_config] includes` in `mise.toml`, so it
  exists here and is simply absent from a generated project. `mise run test` is the *generated*
  project's Django suite and needs a project.

Anything added to the repository is copied into every generated project unless its directory is
named in the `--exclude` flags of the documented command. That includes dot-directories, and it
is the reason `--exclude` is mandatory rather than optional.

### Template Usage

To create a new Django project using this template:

```bash
uv run --with=django django-admin startproject \
    --extension=ini,py,toml,sh \
    --exclude=template_tests \
    --template=https://github.com/oliverandrich/django-project-starter/archive/refs/heads/main.zip \
    your_project_name
```

`--exclude` is required: without it `startproject` drops every dot-directory, `.mise/` among
them, and `template_tests/` would be copied into the new project and rendered as a Django
template. README.md is the authoritative copy of this command — `template_tests/` parses it
from there.

This will replace all `{{ project_name }}` placeholders with your actual project name throughout the codebase.