"""System checks for settings Django itself only warns about.

Outside DEBUG, a missing SECRET_KEY answers every page with 500 and missing ALLOWED_HOSTS with 400.
Django's deploy checks report both as warnings, and /health still answers 200.
"""

from django.conf import settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured


def check_secret_key(app_configs, **kwargs) -> list[checks.CheckMessage]:
    if settings.DEBUG:
        return []
    try:
        # Django refuses to return an empty SECRET_KEY.
        if settings.SECRET_KEY:
            return []
    except ImproperlyConfigured:
        pass
    return [
        checks.Error(
            "SECRET_KEY is empty.",
            hint="Set the SECRET_KEY environment variable.",
            id="settings.E001",
        )
    ]


def check_allowed_hosts(app_configs, **kwargs) -> list[checks.CheckMessage]:
    if settings.DEBUG or settings.ALLOWED_HOSTS:
        return []
    return [
        checks.Error(
            "ALLOWED_HOSTS is empty.",
            hint="Set the ALLOWED_HOSTS environment variable to the site's host names.",
            id="settings.E002",
        )
    ]
