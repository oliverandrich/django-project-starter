from importlib import import_module

from django.apps import AppConfig


class ProjectConfig(AppConfig):
    name = "{{ project_name }}"

    def ready(self) -> None:
        import_module(f"{self.name}.scheduler_lock").install()
