set export
set dotenv-load

@_default:
    just --list

[private]
@check_uv:
    if ! command -v uv &> /dev/null; then \
        echo "uv could not be found. Exiting."; \
        exit; \
    fi

# bootstrap the project
@bootstrap: check_uv
    echo "\033[32m✓\033[0m Created .env file."
    echo "# Activate debug mode for Django framework." >>.env
    echo "DEBUG=true" >>.env

    echo "\033[32m✓\033[0m Installed dependencies."
    uv sync --quiet --all-extras

    echo "\033[32m✓\033[0m Initial built of tailwind.css"
    uv run python manage.py tailwind build 2>&1 >/dev/null

    echo "\033[32m✓\033[0m Initialized git repository."
    git init

    echo "\033[32m✓\033[0m Initial commit."
    git add -A .
    git commit -m "Initial commit"

    echo "\033[32m✓\033[0m Installed pre-commit hook."
    uvx --with pre-commit-uv pre-commit install

    echo
    echo "\033[32mHappy coding!\033[0m"

# upgrade/install all dependencies defined in pyproject.toml
@upgrade: check_uv
    uv sync --upgrade --all-extras

# run database migrations
@migrate *ARGS: check_uv
    uv run manage.py migrate {{ ARGS }}

# create database migrations
@makemigrations *ARGS: check_uv
    uv run manage.py makemigrations {{ ARGS }}

# start debugserver
@debugserver *ARGS: check_uv
    uv run manage.py tailwind runserver {{ ARGS }}

alias runserver := debugserver

# start interactive shell
@shell *ARGS: check_uv
    uv run manage.py shell_plus {{ ARGS }}

# start manage.py for all cases not covered by other commands
@manage *ARGS: check_uv
    uv run manage.py {{ ARGS }}

# run pre-commit rules on all files
@lint: check_uv
    uvx --with pre-commit-uv pre-commit run --all-files

# run test suite
@test: check_uv
    uv run python -m coverage run -m django test --settings tests.settings
    uv run python -m coverage report
