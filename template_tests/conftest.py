"""Fixtures for generating projects from this repository with Copier."""

import shutil
import subprocess
from pathlib import Path

import pytest
from copier import run_copy

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def template_factory(tmp_path_factory: pytest.TempPathFactory):
    """Builds the template from tracked files only, as a clone of the repository holds them.

    Built from the working tree, so uncommitted work is under test, but only for files git
    already knows about. `shutil.copy2` keeps the executable bit, which the mise file tasks need.
    """

    def _build() -> Path:
        staging = tmp_path_factory.mktemp("template")
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True
        ).stdout.decode()
        for relative in filter(None, tracked.split("\0")):
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
def generate(template_dir: Path, tmp_path: Path):
    """Generate a project with Copier and return its root."""

    def _generate(project_name: str = "example_project", **answers) -> Path:
        destination = tmp_path / project_name
        run_copy(
            str(template_dir),
            destination,
            data={"project_name": project_name, "author": "Jane Doe", **answers},
            defaults=True,
            quiet=True,
            # copier.yml runs .mise/tasks/license --fix after generation.
            unsafe=True,
        )
        return destination

    return _generate
