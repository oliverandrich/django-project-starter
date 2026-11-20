"""Django settings for email from an email URL, with MAILERS in place of the EMAIL_* settings.

dj-email-url 1.0.6 returns the EMAIL_* settings, which Django 6.1 deprecates.
"""

from typing import Any
from urllib.parse import urlparse

import dj_email_url

SMTP = "django.core.mail.backends.smtp.EmailBackend"
FILE = "django.core.mail.backends.filebased.EmailBackend"

# Each backend rejects keyword arguments it does not know, so only its own options are passed.
# Keys are backend arguments; values are the dj-email-url settings that hold them.
BACKEND_OPTIONS = {
    SMTP: {
        "host": "EMAIL_HOST",
        "username": "EMAIL_HOST_USER",
        "password": "EMAIL_HOST_PASSWORD",
        "use_tls": "EMAIL_USE_TLS",
        "use_ssl": "EMAIL_USE_SSL",
        "timeout": "EMAIL_TIMEOUT",
    },
    FILE: {"file_path": "EMAIL_FILE_PATH"},
}

ADDRESS_SETTINGS = ("SERVER_EMAIL", "DEFAULT_FROM_EMAIL")


def settings(url: str) -> dict[str, Any]:
    """Return MAILERS, plus SERVER_EMAIL and DEFAULT_FROM_EMAIL when the URL sets them."""
    if not url:
        raise ValueError("EMAIL_URL is empty.")
    try:
        config = dj_email_url.parse(url)
    except ValueError as error:
        raise ValueError(f"EMAIL_URL is invalid: {error}") from error
    if "EMAIL_BACKEND" not in config:
        raise ValueError(f"EMAIL_URL has an unknown scheme: {url.partition(':')[0]}")

    backend = config["EMAIL_BACKEND"]
    options = {arg: config[key] for arg, key in BACKEND_OPTIONS.get(backend, {}).items()}
    if backend == SMTP:
        # Django's EMAIL_HOST defaulted to localhost; an SMTP mailer without a host fails.
        options["host"] = options["host"] or "localhost"
        # dj-email-url fills in 25 or 587 before it reads ?ssl. Without a port in the URL,
        # Django picks 465, 587 or 25 from use_ssl and use_tls.
        options["port"] = urlparse(url).port
    if backend == FILE and not options["file_path"]:
        raise ValueError("EMAIL_URL needs a path for the file backend, such as file:////var/mail.")
    # None means the backend's own default.
    options = {arg: value for arg, value in options.items() if value is not None}

    addresses = {name: config[name] for name in ADDRESS_SETTINGS if name in config}
    return {"MAILERS": {"default": {"BACKEND": backend, "OPTIONS": options}}, **addresses}
