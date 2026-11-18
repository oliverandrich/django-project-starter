"""What `copier copy` must produce from this template."""

import ast
import functools
import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from conftest import REPO_ROOT

PLACEHOLDER = "{{ project" + "_name }}"

# mise's config. test_file_tasks_stay_executable covers the file tasks it references.
MISE_FILES = ("mise.toml",)

# The generated project's GitHub setup. .github is a dot-directory, so it needs --exclude too.
CI_WORKFLOW = ".github/workflows/ci.yml"
GITHUB_FILES = (CI_WORKFLOW, ".github/dependabot.yml")
UV_UPDATES = "package-ecosystem: uv"

# Agent instructions. CLAUDE.md imports AGENTS.md.
AGENT_FILES = ("AGENTS.md", "CLAUDE.md")

# Every login method copier.yml offers.
LOGINS = ["password", "microsoft", "magic_link"]

# The repository's own files, outside template/.
REPOSITORY_FILES = ("template_tests", "copier.yml", ".github/workflows/template.yml")

# `mise run <task>` as the docs spell it, in a shell block or inline in backticks.
DOCUMENTED_TASK = re.compile(r"mise run ([a-z][a-z0-9-]*)")


def _trust(project: Path) -> None:
    subprocess.run(["mise", "trust", "--quiet"], cwd=project, check=True, capture_output=True)


def _stub_env(stubs: Path, bodies: dict[str, str]) -> dict[str, str]:
    """Write shell stubs into `stubs` and return an environment that finds them first on PATH."""
    for name, body in bodies.items():
        (stubs / name).write_text(f"#!/bin/sh\n{body}\n")
        (stubs / name).chmod(0o755)
    return {**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}"}


def _mise_tasks(project: Path) -> list[dict]:
    """The tasks mise sees inside a generated project, excluding the user's own global ones."""
    _trust(project)
    listing = subprocess.run(
        ["mise", "tasks", "--json"],
        cwd=project,
        capture_output=True,
        text=True,
        check=True,
    )
    return [task for task in json.loads(listing.stdout) if not task["global"]]


@functools.cache
def _task_names(root: Path) -> frozenset[str]:
    """Task names and their aliases, since the docs may name a task by its alias."""
    names = set()
    for task in _mise_tasks(root):
        names.add(task["name"])
        names.update(task["aliases"])
    return frozenset(names)


def _text_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            yield path, path.read_text()
        except UnicodeDecodeError:
            continue


def test_tooling_lands_in_the_generated_project(generate):
    project = generate()
    expected = (*MISE_FILES, *GITHUB_FILES, *AGENT_FILES, ".copier-answers.yml")
    missing = [name for name in expected if not (project / name).is_file()]
    assert missing == []


def test_repository_files_stay_behind(generate):
    """The tests, the Copier config and the template's own CI are not part of a project."""
    project = generate()
    assert [name for name in REPOSITORY_FILES if (project / name).exists()] == []


def test_readme_documents_copier_copy():
    assert "copier copy" in (REPO_ROOT / "README.md").read_text()


def test_file_tasks_stay_executable(generate, template_dir):
    """mise skips a file task without the executable bit, and says nothing about it.

    A file task that was not copied fails only when someone runs it, so this checks every one.
    """
    project = generate()
    source = template_dir / "template"
    tasks = [path.relative_to(source) for path in (source / ".mise/tasks").iterdir()]
    assert tasks, "the template has no file tasks: the test is not looking anywhere"
    not_executable = [str(task) for task in tasks if not os.access(project / task, os.X_OK)]
    assert not_executable == []


def test_every_rendered_file_loses_its_placeholder_and_suffix(generate, template_dir):
    """Copier renders exactly the .jinja files and drops the suffix."""
    project = generate("acme_shop")
    source = template_dir / "template"
    rendered = [path for path in source.rglob("*.jinja") if "_copier_conf" not in path.name]
    assert rendered, "no .jinja files in the template: the test is not looking anywhere"
    assert list(project.rglob("*.jinja")) == []
    offenders = [
        str(path.relative_to(project))
        for path in project.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".toml", ".md"}
        and PLACEHOLDER in path.read_text()
    ]
    assert offenders == []


@pytest.mark.parametrize("login", [[], ["password"], ["microsoft"], ["magic_link"], LOGINS])
@pytest.mark.parametrize("background_tasks", [True, False])
@pytest.mark.parametrize("live_updates", [True, False])
def test_every_generated_python_file_parses(generate, live_updates, background_tasks, login):
    """A conditional that renders into an invalid position would pass every other test here."""
    project = generate(
        "acme_shop", live_updates=live_updates, background_tasks=background_tasks, login=login
    )

    checked, broken = 0, []
    for path in sorted(project.rglob("*.py")):
        checked += 1
        try:
            ast.parse(path.read_text())
        except SyntaxError as error:
            broken.append(f"{path.relative_to(project)}: {error}")

    assert checked, "no Python files in the generated project — the test is not looking anywhere"
    assert broken == []


def test_package_directory_is_renamed(generate):
    project = generate("acme_shop")
    assert (project / "acme_shop" / "settings.py").is_file()
    assert not (project / PLACEHOLDER).exists()


@pytest.mark.parametrize("background_tasks", [True, False])
def test_mise_toml_carries_no_placeholder(generate, background_tasks):
    """mise renders its own config as Tera, which spells interpolation with doubled braces too."""
    project = generate(background_tasks=background_tasks)
    for config in (REPO_ROOT / "mise.toml", project / "mise.toml"):
        assert "{" + "{" not in config.read_text()


def test_no_task_points_at_something_left_out_of_the_project(generate, template_dir):
    """A task naming a path that generation does not produce is dead on arrival.

    The old justfile had this bug — `--settings tests.settings`, a module that never existed —
    and it recurred while writing this one, as a `test-template` task pointing at the
    deliberately excluded `template_tests/`. So the guard is against the class, not the instance:
    anything a task names that exists here but not in a generated project.
    """
    project = generate()

    offenders = []
    for task in _mise_tasks(project):
        run = task["run"]
        command = " ".join(run) if isinstance(run, list) else str(run)
        for token in re.findall(r"[\w./-]+", command):
            if (template_dir / "template" / token).exists() and not (project / token).exists():
                offenders.append(f"{task['name']}: {token}")

    assert offenders == []


def test_every_documented_command_is_a_real_task(generate):
    """Every `mise run X` the docs promise has to resolve to a task that exists.

    This replaced a pair of tests that asserted the justfile was gone and that no `just X` call
    survived. Those pinned a migration that has happened rather than a property of the template:
    once green they could never fail again for a reason anybody cares about. Docs drifting from
    tasks is the failure that actually recurs — and it is the same class as the bug the old
    justfile shipped, a documented `coverage` recipe that was never defined.

    The documents describe different things. README.md, AGENTS.md and the CI workflow describe a
    generated project. CLAUDE.md describes this repository, whose tasks include `test-template`.
    """
    project = generate()

    missing, documented = [], 0
    for document, root, where in (
        (REPO_ROOT / "README.md", project, "a generated project"),
        (project / CI_WORKFLOW, project, "a generated project"),
        (project / "AGENTS.md", project, "a generated project"),
        (REPO_ROOT / "CLAUDE.md", REPO_ROOT, "the template repository"),
    ):
        available = _task_names(root)
        for name in sorted(set(DOCUMENTED_TASK.findall(document.read_text()))):
            documented += 1
            if name not in available:
                missing.append(f"{document} promises `mise run {name}`, absent in {where}")

    assert documented, "the docs name no mise commands — the test is not looking anywhere"
    assert missing == []


def test_template_dependabot_skips_uv():
    """uv cannot read the placeholder pyproject.toml, so its updates would fail every week here."""
    assert UV_UPDATES not in (REPO_ROOT / ".github/dependabot.yml").read_text()


def test_claude_md_imports_agents_md(generate):
    """Claude Code does not read AGENTS.md itself, so CLAUDE.md has to import it."""
    assert (generate() / "CLAUDE.md").read_text() == "@AGENTS.md\n"


def test_bootstrap_commits_the_project_and_warns_without_a_database(generate, tmp_path_factory):
    """mise, uv and uvx are stubbed: this checks the script's logic, not the toolchain.

    The template workflow's end-to-end job runs the real bootstrap.
    """
    project = generate()
    stubs = tmp_path_factory.mktemp("stubs")
    stub_bodies = {
        "mise": f'echo "{stubs}/python"',
        "python": 'echo "Python 3.14.0"',
        # createdb fails as it does without a reachable PostgreSQL server.
        "uv": f'echo "uv $*" >> "{stubs}/uv.calls"; case "$*" in *createdb*) exit 1;; esac',
        "uvx": ":",
    }
    env = {
        **_stub_env(stubs, stub_bodies),
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    env.pop("MISE_PROJECT_ROOT", None)
    bootstrap = subprocess.run(
        [".mise/tasks/bootstrap"], cwd=project, env=env, check=True, capture_output=True, text=True
    )

    committed = subprocess.run(
        ["git", "ls-files"], cwd=project, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert CI_WORKFLOW in committed
    assert ".copier-answers.yml" in committed
    assert UV_UPDATES in (project / ".github/dependabot.yml").read_text()
    assert "uv run python manage.py createdb" in (stubs / "uv.calls").read_text().splitlines()
    assert "DATABASE_URL" in bootstrap.stdout + bootstrap.stderr


def _run_entrypoint(project: Path, stubs: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run docker/entrypoint.sh with python and granian replaced by stubs that echo their argv."""
    env = _stub_env(stubs, {name: f'echo "{name} $*"' for name in ("python", "granian")})
    return subprocess.run(
        ["docker/entrypoint.sh", *args], cwd=project, env=env, capture_output=True, text=True
    )


def test_entrypoint_starts_each_process(generate, tmp_path_factory):
    """One image runs the web server, the task worker and the cron scheduler."""
    project = generate("acme_shop")
    stubs = tmp_path_factory.mktemp("stubs")

    web = _run_entrypoint(project, stubs).stdout.splitlines()
    # Deploy checks fail on errors before anything touches the database.
    assert web[0] == "python manage.py check --deploy --fail-level ERROR"
    assert web.index("python manage.py migrate") > 0
    assert web[-1] == "python manage.py serve"

    worker = _run_entrypoint(project, stubs, "worker").stdout.splitlines()
    assert worker == ["python manage.py db_worker"]

    scheduler = _run_entrypoint(project, stubs, "scheduler").stdout.splitlines()
    assert scheduler == ["python manage.py crontask --no-heartbeat"]

    # Any other command runs as given, so one-off commands such as createsuperuser still work.
    other = _run_entrypoint(project, stubs, "python", "manage.py", "createsuperuser")
    assert other.stdout.splitlines() == ["python manage.py createsuperuser"]


def test_dockerfile_runs_the_entrypoint_unbuffered(generate):
    """No docker build runs here, so the Dockerfile lines themselves are checked.

    With CMD alone, `docker run <image> worker` would replace the script instead of naming it.
    Without a tty, Python buffers stdout, and container logs would show output only at exit.
    """
    dockerfile = (generate() / "docker/Dockerfile").read_text()
    assert 'ENTRYPOINT ["docker/entrypoint.sh"]' in dockerfile
    assert 'CMD ["web"]' in dockerfile
    assert "ENV PYTHONUNBUFFERED=1" in dockerfile
    # manage.py serve runs granian, which otherwise binds to 127.0.0.1 inside the container.
    assert "ENV GRANIAN_HOST=0.0.0.0" in dockerfile


def test_debugserver_runs_server_tailwind_worker_and_scheduler(generate):
    """mise runs the dependencies in parallel, and Ctrl-C stops all of them."""
    tasks = {task["name"]: task for task in _mise_tasks(generate())}
    assert sorted(tasks["debugserver"]["depends"]) == ["scheduler", "serve", "tailwind", "worker"]


def test_without_background_tasks_debugserver_runs_server_and_tailwind(generate):
    tasks = {task["name"]: task for task in _mise_tasks(generate(background_tasks=False))}
    assert sorted(tasks["debugserver"]["depends"]) == ["serve", "tailwind"]
    assert "worker" not in tasks
    assert "scheduler" not in tasks


def test_mise_disables_output_buffering(generate):
    """debugserver pipes each task's output, and Python buffers a pipe until the process exits."""
    project = generate()
    _trust(project)
    listing = subprocess.run(
        ["mise", "env", "--json"], cwd=project, capture_output=True, text=True, check=True
    )
    assert json.loads(listing.stdout)["PYTHONUNBUFFERED"] == "1"


def test_project_ci_runs_unconditionally(generate):
    """ci.yml no longer needs a guard: this repository does not run it."""
    assert "\n    if:" not in (generate() / CI_WORKFLOW).read_text()


def test_answers_file_records_the_choices(generate):
    """copier update reads the answers back, so they must survive generation."""
    answers = (generate("acme_shop", live_updates=False) / ".copier-answers.yml").read_text()
    assert "project_name: acme_shop" in answers.splitlines()
    assert "live_updates: false" in answers.splitlines()


def test_without_background_tasks_nothing_names_them(generate):
    project = generate("acme_shop", background_tasks=False)
    offenders = [
        str(path.relative_to(project))
        for path in project.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".toml", ".md", ".yml", ".sh"}
        and re.search(
            r"django_tasks_db|django-tasks-db|crontask|db_worker|scheduler_lock", path.read_text()
        )
    ]
    assert offenders == []
    assert not (project / "acme_shop" / "tasks.py").exists()
    entrypoint = (project / "docker/entrypoint.sh").read_text()
    assert "worker)" not in entrypoint
    assert "scheduler)" not in entrypoint


def test_live_updates_without_background_tasks_documents_the_pruning(generate):
    """Without a scheduler, nothing deletes old events unless the project runs the command."""
    project = generate("acme_shop", background_tasks=False)
    assert "manage.py prune_stream_events" in (project / "AGENTS.md").read_text()


def test_without_login_only_the_admin_logs_in(generate):
    project = generate("acme_shop")
    offenders = [
        str(path.relative_to(project))
        for path in project.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".toml", ".html"}
        and re.search(r"django_auth_adfs|django-auth-adfs|sesame|LOGIN_METHODS", path.read_text())
    ]
    assert offenders == []
    assert not (project / "acme_shop" / "login.py").exists()
    assert not (project / "acme_shop" / "templates" / "registration").exists()


def test_the_user_model_exists_without_login(generate):
    """AUTH_USER_MODEL cannot change after the first migration, so every project has it."""
    project = generate("acme_shop")
    assert 'AUTH_USER_MODEL = "acme_shop.User"' in (project / "acme_shop/settings.py").read_text()
    assert (project / "acme_shop/migrations/0001_initial.py").is_file()


def test_login_methods_render_as_a_python_list(generate):
    settings = (generate("acme_shop", login=LOGINS) / "acme_shop/settings.py").read_text()
    assert 'LOGIN_METHODS = ["password", "microsoft", "magic_link"]' in settings.splitlines()


def test_internal_domains_come_with_magic_links(generate):
    """The setting exists with links; the deploy check demands it only together with Microsoft."""
    links = generate("acme_shop", login=["magic_link"])
    microsoft = generate("other_shop", login=["microsoft"])
    assert "INTERNAL_EMAIL_DOMAINS" in (links / "acme_shop/settings.py").read_text()
    assert "INTERNAL_EMAIL_DOMAINS" not in (microsoft / "other_shop/settings.py").read_text()


def test_without_live_updates_nothing_names_django_pg_sse(generate):
    project = generate("acme_shop", live_updates=False)
    offenders = [
        str(path.relative_to(project))
        for path in project.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".toml", ".md", ".yml"}
        and re.search(r"pg[_-]sse", path.read_text())
    ]
    assert offenders == []
    assert not (project / "acme_shop" / "events.py").exists()


def test_update_htmx_rejects_anything_but_a_4x_release(generate):
    """A dist-tag such as "latest" would vendor an unknown release; htmx 2 lacks hx-sse."""
    project = generate()
    for version in ("latest", "2.0.4", ""):
        result = subprocess.run(
            [".mise/tasks/update-htmx", version], cwd=project, capture_output=True, text=True
        )
        assert result.returncode != 0
        assert "4.x" in result.stderr
    assert (project / "assets/vendor/htmx/VERSION").read_text().strip().startswith("4.")


def test_ruff_skips_migrations_named_on_the_command_line(generate):
    """pre-commit passes file names, which bypass ruff's `exclude` unless `force-exclude` is set."""
    project = generate("acme_shop")
    rev = re.search(
        r"ruff-pre-commit\n\s+(?:#.*\n\s+)*rev: v?(\S+)",
        (project / ".pre-commit-config.yaml").read_text(),
    )
    assert rev, "no ruff-pre-commit revision in .pre-commit-config.yaml"
    migration = project / "acme_shop" / "migrations" / "0001_initial.py"
    migration.write_text(f"x = {'1 + ' * 40}1\n")
    for command in (["check"], ["format", "--check"]):
        result = subprocess.run(
            ["uvx", f"ruff@{rev[1]}", *command, str(migration.relative_to(project))],
            cwd=project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
