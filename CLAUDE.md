# CLAUDE.md

@template/AGENTS.md.jinja

The import above describes the project this template generates. Its `<package>` is
`template/{{ project_name }}/` here. The rest of this file concerns the template repository.

## Working on the template itself

This repository is a [Copier](https://copier.readthedocs.io/) template.

- `copier.yml` holds the questions: `project_name` and `live_updates`.
- `template/` holds the generated project. Nothing outside it reaches a project.
- Copier renders only files ending in `.jinja` and drops the suffix. Every other file is copied
  unchanged, so Django templates keep their own `{{ }}` and `{% %}`.
- A `.jinja` file that contains Django template syntax wraps it in `{% raw %}`, as
  `AGENTS.md.jinja` does.
- `trim_blocks` is on: a line that holds only `{% if %}` or `{% endif %}` disappears.
- A file that exists only with an answer has a conditional name, such as
  `{% if live_updates %}events.py{% endif %}`.

`mise run test-template` generates projects through Copier's Python API and checks them.
`mise run lint` lints `template_tests/`. The `.jinja` files are not valid Python, so ruff and
basedpyright check them only in a generated project. The template workflow does that for each
value of `live_updates`.

Two workflows exist:

- `template/.github/workflows/ci.yml` belongs to the generated project.
- `.github/workflows/template.yml` tests this repository and stays here.

## Template usage

README.md documents `copier copy` and `copier update`.
