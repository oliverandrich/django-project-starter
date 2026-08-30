"""Fixtures for running `django-admin startproject` against this repository.

The command under test is the one README.md documents, parsed out of the README rather than
written down a second time here — a template whose documented install command differs from the
tested one is the failure these tests exist to prevent.
"""

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _documented_command() -> list[str]:
    """The `django-admin startproject` invocation from README.md, as an argv list."""
    lines = (REPO_ROOT / "README.md").read_text().splitlines()
    start = next(
        (index for index, line in enumerate(lines) if "django-admin startproject" in line),
        None,
    )
    if start is None:
        raise AssertionError("README.md no longer documents a startproject command")

    chunk = []
    for line in lines[start:]:
        chunk.append(line.strip())
        if not line.rstrip().endswith("\\"):
            break
    command = " ".join(part.rstrip("\\").strip() for part in chunk)
    return shlex.split(command.removeprefix("$ "))


@pytest.fixture(scope="session")
def documented_argv() -> list[str]:
    return _documented_command()


@pytest.fixture(scope="session")
def template_factory(tmp_path_factory: pytest.TempPathFactory):
    """Builds the template as startproject sees it over the wire: tracked files only.

    Built from the working tree, so uncommitted work is under test — but only for files git
    already knows about. A file that has never been `git add`ed is invisible here for the same
    reason it is invisible in the published zip, and that is deliberate: it is the same trap
    `pre-commit run --all-files` has.

    `shutil.copy2` keeps the executable bit, which the mise file tasks depend on.
    """

    def _build(*, omit: tuple[str, ...] = ()) -> Path:
        staging = tmp_path_factory.mktemp("template")
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode()

        for relative in filter(None, tracked.split("\0")):
            if relative.split("/")[0] in omit:
                continue
            source = REPO_ROOT / relative
            if not source.exists():  # tracked but deleted in the working tree
                continue
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        return staging

    return _build


@pytest.fixture(scope="session")
def template_dir(template_factory) -> Path:
    return template_factory()


@pytest.fixture
def run_startproject(template_dir: Path, documented_argv: list[str], tmp_path: Path):
    """Run the documented command against a local checkout, successful or not."""

    def _run(
        project_name: str = "example_project",
        *,
        argv: list[str] | None = None,
        template: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        argv = [
            f"--template={template or template_dir}" if arg.startswith("--template=") else arg
            for arg in (documented_argv if argv is None else argv)
        ]
        argv[-1] = project_name

        # Without this, `uv run` layers --with=django onto whatever venv happens to be active
        # and django-admin comes from an unrelated project — the result then depends on where
        # the suite was started from.
        env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}

        return subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, env=env)

    return _run


@pytest.fixture
def generate(run_startproject, tmp_path: Path):
    """Generate a project and return its root, insisting that generation succeeded."""

    def _generate(project_name: str = "example_project", **kwargs) -> Path:
        result = run_startproject(project_name, **kwargs)
        assert result.returncode == 0, f"startproject failed:\n{result.stderr}"
        return tmp_path / project_name

    return _generate
