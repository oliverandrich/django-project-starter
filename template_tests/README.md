# template_tests

Tests for the template itself — that `django-admin startproject` turns this repository into a
working project. They are not part of the generated project and must never ship into one, which
is why `template_tests` is named in the `--exclude` flags of the documented install command.

Run them with `mise run test-template`.
