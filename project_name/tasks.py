"""Tasks of the project. `manage.py crontask` imports this module to register `@cron` schedules."""

from datetime import timedelta
from importlib import import_module

from crontask import cron
from django.conf import settings
from django.core.management import call_command
from django.tasks import DEFAULT_TASK_BACKEND_ALIAS, task, task_backends
from django.utils import timezone
from django_tasks_db import DatabaseBackend

# A string, so the template repository stays valid Python before startproject renders it.
StreamEvent = import_module("{{ project_name }}.models").StreamEvent


@cron("0 3 * * *")
@task
def prune_task_results() -> None:
    """Delete finished task results older than two weeks from every queue."""
    # prune_db_task_results rejects any other backend.
    if isinstance(task_backends[DEFAULT_TASK_BACKEND_ALIAS], DatabaseBackend):
        call_command("prune_db_task_results", queue_name="*", min_age_days=14, verbosity=0)


@cron("17 * * * *")
@task
def prune_stream_events() -> None:
    """Delete server-sent events older than EVENTS_RETENTION_HOURS, the reach of Last-Event-ID."""
    cutoff = timezone.now() - timedelta(hours=settings.EVENTS_RETENTION_HOURS)
    StreamEvent.objects.filter(created__lt=cutoff).delete()
