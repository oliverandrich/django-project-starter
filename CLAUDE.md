# CLAUDE.md

@AGENTS.md

AGENTS.md describes the project this template generates. Its `<package>` is `project_name/` here.
The rest of this file concerns the template repository itself.

## Working on the template itself

This repository is a template for `django-admin startproject`. Generation replaces every
`{{ project_name }}` placeholder and renames `project_name/`. Two things follow from that:

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

Two workflows live in `.github/workflows/`:

- `ci.yml` belongs to the generated project. It is disabled in this repository, where it cannot pass.
- `template.yml` tests this repository. It ships with every project, and `mise run bootstrap`
  deletes it there.

Files named `*.project.*` belong to the generated project. `mise run bootstrap` renames each
listed one to the name without `.project`, replacing this repository's version:

- `.github/dependabot.project.yml` becomes `.github/dependabot.yml`.
- `CLAUDE.project.md` becomes `CLAUDE.md` and only imports `AGENTS.md`.

Anything added to the repository is copied into every generated project unless its directory is
named in the `--exclude` flags of the documented command. That includes dot-directories, and it
is the reason `--exclude` is mandatory rather than optional.

## Template usage

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