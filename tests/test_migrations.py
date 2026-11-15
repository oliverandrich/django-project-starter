from django.core.management import call_command
from django.test import TestCase


class MigrationsTest(TestCase):
    # makemigrations checks the migration history in the database.
    def test_models_and_migrations_agree(self):
        # makemigrations --check exits non-zero when a model change lacks a migration.
        call_command("makemigrations", "--check", "--dry-run", verbosity=0)
