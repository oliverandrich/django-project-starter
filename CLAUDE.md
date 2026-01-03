# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Django project template** for use with `django-admin startproject`. It provides a batteries-included starter template with modern tooling and best practices. When using this template, `{{ project_name }}` placeholders will be replaced with the actual project name.

## Common Development Commands

### Project Setup
```bash
# Bootstrap new project (first time only)
just bootstrap

# Install/upgrade all dependencies
just upgrade
```

### Development Server
```bash
# Start development server with Tailwind CSS hot-reload
just runserver
# or
just debugserver
```

### Database Operations
```bash
# Run migrations
just migrate

# Create new migrations
just makemigrations
```

### Testing and Quality
```bash
# Run test suite with coverage
just test

# Run all pre-commit checks (linting, formatting, type checking)
just lint

# Run specific linters if needed
uv run ruff check .
uv run ruff format .
uv run pyright .
```

### Interactive Shell
```bash
# Start Django shell with shell_plus
just shell
```

### Other Django Commands
```bash
# For any other manage.py commands
just manage <command>
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
- **`assets/`**: Static assets (CSS, JS) served by WhiteNoise
- **`logs/`**: Log files from management commands (gitignored)
- **`docker/`**: Docker configuration with Granian ASGI server

### Technology Stack

- **Frontend**: HTMX + Tailwind CSS (via django-tailwind-cli with DaisyUI)
- **Backend**: Django 6.0 with django-htmx, django-typer for CLI commands
- **Database**: SQLite with optimized settings (can switch to PostgreSQL/MySQL via DATABASE_URL)
- **Security**: Argon2 password hashing, environment-based configuration
- **Development Tools**:
  - `uv` for dependency management
  - `just` for task automation
  - Pre-commit hooks with ruff, pyright, django-upgrade
  - Type checking with pyright and django-types

### Configuration

The project uses environment variables for configuration with sensible defaults for development:
- Create a `.env` file for local development (auto-created by `just bootstrap`)
- Key settings: `DEBUG`, `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`
- Email configuration via `EMAIL_URL`
- Cache configuration via `CACHE_URL`

### Custom Features

1. **BaseCommand**: All management commands should inherit from `project_name.management.base.BaseCommand` for automatic rotating log file handling
2. **Template Builtins**: Common templatetags (i18n, static, heroicons) are pre-loaded
3. **Optimized SQLite**: Includes performance optimizations for SQLite when used
4. **Static File Serving**: WhiteNoise configured for production-ready static file serving

### Template Usage

To create a new Django project using this template:

```bash
uv run --with=django django-admin startproject \
    --extension=ini,py,toml,sh \
    --template=https://codeberg.org/oliverandrich/django-project-starter/archive/main.zip \
    your_project_name
```

This will replace all `{{ project_name }}` placeholders with your actual project name throughout the codebase.