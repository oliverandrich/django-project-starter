"""Create the database that DATABASE_URL names, unless it exists."""

from importlib import import_module
from typing import Any

from django.db import connection

# A string, so the template repository stays valid Python before startproject renders it.
base = import_module("{{ project_name }}.management.base")


@base.command()
@base.pass_logger
def main(logger):
    name = connection.settings_dict["NAME"]
    if not name:
        logger.info("DATABASES has no NAME; the PostgreSQL service file names the database.")
        return
    # Django's own test database creation uses this connection: it reaches the server without the
    # target database and falls back to another database when "postgres" is unavailable.
    # Private API, so the stubs leave it out.
    with connection._nodb_cursor() as cursor:  # pyright: ignore[reportAttributeAccessIssue]
        creation: Any = connection.creation
        if creation._database_exists(cursor, name):
            logger.info("Database %s exists.", name)
            return
        cursor.execute(f"CREATE DATABASE {connection.ops.quote_name(name)}")
        logger.info("Created database %s.", name)
