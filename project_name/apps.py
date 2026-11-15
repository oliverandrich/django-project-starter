from importlib import import_module

from django.apps import AppConfig
from django.contrib.auth.signals import user_logged_out
from django.db.models.signals import post_migrate


class ProjectConfig(AppConfig):
    name = "{{ project_name }}"

    def ready(self) -> None:
        import_module(f"{self.name}.scheduler_lock").install()
        cache = import_module(f"{self.name}.cache")
        post_migrate.connect(cache.create_cache_tables, sender=self)
        events = import_module(f"{self.name}.events")
        user_logged_out.connect(events.close_session_streams)
