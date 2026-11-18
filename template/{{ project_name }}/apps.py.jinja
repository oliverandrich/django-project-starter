from importlib import import_module

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ProjectConfig(AppConfig):
    name = "{{ project_name }}"

    def ready(self) -> None:
        import_module(f"{self.name}.scheduler_lock").install()
        log_config = import_module(f"{self.name}.log_config")
        # Here, not in settings: evaluating the settings again would replace the processor list
        # that cached loggers hold.
        log_config.configure()
        log_config.connect()
        cache = import_module(f"{self.name}.cache")
        post_migrate.connect(cache.create_cache_tables, sender=self)
