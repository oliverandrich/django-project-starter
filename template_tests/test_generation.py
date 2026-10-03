"""What `django-admin startproject` must produce from this template."""

import ast
import functools
import json
import os
import re
import subprocess
from pathlib import Path

from conftest import REPO_ROOT

PLACEHOLDER = "{{ project" + "_name }}"  # split so this file is not itself a template

# Everything mise needs to drive a generated project. `mise.toml` alone is not enough: it
# references file tasks, and a file task that was not copied fails only when someone runs it.
MISE_FILES = ("mise.toml", ".mise/tasks/dev", ".mise/tasks/bootstrap")

# The generated project's GitHub setup. .github is a dot-directory, so it needs --exclude too.
CI_WORKFLOW = ".github/workflows/ci.yml"
PROJECT_DEPENDABOT = ".github/dependabot.project.yml"
GITHUB_FILES = (CI_WORKFLOW, PROJECT_DEPENDABOT)
UV_UPDATES = "package-ecosystem: uv"

# Agent instructions. Bootstrap renames CLAUDE.project.md to CLAUDE.md, which imports AGENTS.md.
AGENT_FILES = ("AGENTS.md", "CLAUDE.project.md")

# The template repository's own CI. It ships with every project, and bootstrap removes it.
TEMPLATE_WORKFLOW = ".github/workflows/template.yml"

# README.md and CLAUDE.md keep the placeholder on purpose — they document it.
PLACEHOLDER_IS_DOCUMENTED = {"README.md", "CLAUDE.md"}

# `mise run <task>` as the docs spell it, in a shell block or inline in backticks.
DOCUMENTED_TASK = re.compile(r"mise run ([a-z][a-z0-9-]*)")


def _mise_tasks(project: Path) -> list[dict]:
    """The tasks mise sees inside a generated project, excluding the user's own global ones."""
    subprocess.run(["mise", "trust", "--quiet"], cwd=project, check=True, capture_output=True)
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
    """Task names and their aliases — the docs use `mise run runserver`, an alias of debugserver."""
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


def test_documented_command_passes_exclude(documented_argv):
    """Without --exclude, startproject drops every dot-directory — .mise with them.

    django/core/management/templates.py branches on whether the option was passed at all
    (`if "exclude" not in options`), not on its value, so the flag has to be there.
    """
    assert any(arg.startswith(("-x", "--exclude")) for arg in documented_argv)


def test_tooling_lands_in_the_generated_project(generate):
    project = generate()
    expected = MISE_FILES + GITHUB_FILES + AGENT_FILES
    missing = [name for name in expected if not (project / name).is_file()]
    assert missing == []


def test_dot_directories_vanish_without_exclude(generate, documented_argv, template_factory):
    """Pins the Django behaviour the --exclude flags exist for.

    If a future Django release stops dropping dot-directories, this test fails and tells us the
    flags are no longer load-bearing — rather than the template silently depending on them.

    template_tests/ is left out of the template here for the same reason the real command
    excludes it: startproject would otherwise render these very files as Django templates.
    """
    argv = [arg for arg in documented_argv if not arg.startswith(("-x", "--exclude"))]
    project = generate(argv=argv, template=template_factory(omit=("template_tests",)))

    assert not (project / ".mise").exists()
    assert (project / "mise.toml").is_file()  # a plain file, so it still arrives


def test_template_tests_stay_behind(generate):
    """These tests are the template's own machinery and must not ship into a project."""
    project = generate()
    assert not (project / "template_tests").exists()


def test_file_tasks_stay_executable(generate):
    """mise skips a file task without the executable bit, and says nothing about it."""
    project = generate()
    not_executable = [
        name
        for name in (".mise/tasks/dev", ".mise/tasks/bootstrap")
        if not os.access(project / name, os.X_OK)
    ]
    assert not_executable == []


def test_every_placeholder_in_the_template_is_substituted(generate, template_dir):
    """Driven from the template, not from the documented command.

    Asking "does any rendered file still contain a placeholder" and deriving the set of rendered
    files from the same `--extension` flag that decides what gets rendered is circular: an
    extension missing from the command is then also missing from the test. This asks the
    question from the other side — every tracked file that carries the placeholder must come out
    without it — so a file the command forgets to render shows up here.
    """
    project = generate("acme_shop")

    carriers, offenders = [], []
    for source, content in _text_files(template_dir):
        relative = source.relative_to(template_dir)
        if relative.parts[0] == "template_tests" or str(relative) in PLACEHOLDER_IS_DOCUMENTED:
            continue
        if PLACEHOLDER not in content:
            continue
        carriers.append(str(relative))
        # The package directory is renamed as part of generation.
        parts = ["acme_shop" if part == "project_name" else part for part in relative.parts]
        generated = project.joinpath(*parts)
        if not generated.is_file() or PLACEHOLDER in generated.read_text():
            offenders.append(str(relative))

    assert carriers, "no template file carries the placeholder — the test is not looking anywhere"
    assert offenders == []


def test_every_generated_python_file_parses(generate):
    """The only test here that looks at the output as a program rather than as filenames.

    A placeholder that renders into a syntactically invalid position would pass every other
    assertion in this file.
    """
    project = generate("acme_shop")

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
    assert not (project / "project_name").exists()


def test_mise_toml_carries_no_django_placeholder():
    """mise renders its own config as Tera, which spells interpolation with doubled braces too.

    A placeholder in mise.toml would be substituted for a generated project but would break
    `mise run` in this repository, where nothing substitutes it.
    """
    assert "{" + "{" not in (REPO_ROOT / "mise.toml").read_text()


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
            if (template_dir / token).exists() and not (project / token).exists():
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
        ("README.md", project, "a generated project"),
        (CI_WORKFLOW, project, "a generated project"),
        ("AGENTS.md", project, "a generated project"),
        ("CLAUDE.md", REPO_ROOT, "the template repository"),
    ):
        available = _task_names(root)
        for name in sorted(set(DOCUMENTED_TASK.findall((REPO_ROOT / document).read_text()))):
            documented += 1
            if name not in available:
                missing.append(f"{document} promises `mise run {name}`, absent in {where}")

    assert documented, "the docs name no mise commands — the test is not looking anywhere"
    assert missing == []


def test_template_dependabot_skips_uv():
    """uv cannot read the placeholder pyproject.toml, so its updates would fail every week here."""
    assert UV_UPDATES not in (REPO_ROOT / ".github/dependabot.yml").read_text()


def test_template_claude_md_imports_agents_md():
    """Claude Code does not read AGENTS.md itself, so CLAUDE.md has to import it."""
    assert "@AGENTS.md" in (REPO_ROOT / "CLAUDE.md").read_text().splitlines()


def test_bootstrap_swaps_in_the_project_files(generate, template_dir, tmp_path_factory):
    """Template-only files ship with every project; bootstrap swaps in the *.project.* versions.

    mise, uv and uvx are stubbed: this checks the script's logic, not the toolchain. The template
    workflow's end-to-end job runs the real bootstrap.
    """
    project = generate()
    assert (project / TEMPLATE_WORKFLOW).is_file()
    # A project file that merely looks like a template one. Bootstrap may run again later.
    (project / "fixtures").mkdir()
    (project / "fixtures/initial.project.json").write_text("[]")

    stubs = tmp_path_factory.mktemp("stubs")
    for name, body in (
        ("mise", f'echo "{stubs}/python"'),
        ("python", 'echo "Python 3.14.0"'),
        ("uv", ":"),
        ("uvx", ":"),
    ):
        (stubs / name).write_text(f"#!/bin/sh\n{body}\n")
        (stubs / name).chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    env.pop("MISE_PROJECT_ROOT", None)
    subprocess.run([".mise/tasks/bootstrap"], cwd=project, env=env, check=True, capture_output=True)

    committed = subprocess.run(
        ["git", "ls-files"], cwd=project, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert not (project / TEMPLATE_WORKFLOW).exists()
    assert TEMPLATE_WORKFLOW not in committed
    assert CI_WORKFLOW in committed
    # Every *.project.* file of the template, so a new one cannot slip past bootstrap's list.
    for source in template_dir.rglob("*.project.*"):
        swapped = str(source.relative_to(template_dir))
        assert swapped not in committed
        assert swapped.replace(".project.", ".") in committed
    assert (project / "fixtures/initial.project.json").is_file()
    assert (project / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    assert UV_UPDATES in (project / ".github/dependabot.yml").read_text()
