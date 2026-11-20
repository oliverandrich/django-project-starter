from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
from django.test import SimpleTestCase

from tests.utils import evaluate_settings

SMTP = "django.core.mail.backends.smtp.EmailBackend"


def default_mailer(**environ: str) -> dict:
    return evaluate_settings(**environ)["MAILERS"]["default"]


def smtp_backend(url: str) -> SMTPBackend:
    """Build the SMTP backend as Django's mailers do, which validates the OPTIONS."""
    mailer = default_mailer(EMAIL_URL=url)
    assert mailer["BACKEND"] == SMTP
    return SMTPBackend(alias="default", **mailer["OPTIONS"])


class MailersSettingTest(SimpleTestCase):
    def test_console_by_default(self):
        self.assertEqual(
            default_mailer(),
            {"BACKEND": "django.core.mail.backends.console.EmailBackend", "OPTIONS": {}},
        )

    def test_submission_url_configures_smtp_with_tls(self):
        backend = smtp_backend("submission://app:s%40cret@mail.example.com")
        self.assertEqual(
            (backend.host, backend.port, backend.username, backend.password, backend.use_tls),
            ("mail.example.com", 587, "app", "s@cret", True),
        )

    def test_ssl_without_a_port_uses_port_465(self):
        backend = smtp_backend("smtp://mail.example.com?ssl=true")
        self.assertEqual((backend.port, backend.use_ssl), (465, True))

    def test_query_arguments_reach_the_backend(self):
        backend = smtp_backend("smtp://mail.example.com:2525?timeout=10")
        self.assertEqual((backend.port, backend.timeout), (2525, 10))

    def test_smtp_without_a_host_uses_localhost(self):
        # Django's EMAIL_HOST defaulted to localhost; MAILERS has no such default.
        backend = smtp_backend("submission://app:secret@")
        self.assertEqual((backend.host, backend.port), ("localhost", 587))

    def test_file_url_sets_the_path(self):
        # dj-email-url drops the first slash of the path, so an absolute path needs four.
        mailer = default_mailer(EMAIL_URL="file:////var/mail/app")
        self.assertEqual(mailer["OPTIONS"], {"file_path": "/var/mail/app"})

    def test_file_url_without_a_path_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "EMAIL_URL"):
            evaluate_settings(EMAIL_URL="file://")

    def test_from_addresses_come_from_the_url(self):
        url = "console:?_server_email=ops@example.com&_default_from_email=hello@example.com"
        settings = evaluate_settings(EMAIL_URL=url)
        self.assertEqual(settings["SERVER_EMAIL"], "ops@example.com")
        self.assertEqual(settings["DEFAULT_FROM_EMAIL"], "hello@example.com")

    def test_unknown_scheme_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "EMAIL_URL"):
            evaluate_settings(EMAIL_URL="carrier-pigeon://loft")

    def test_empty_url_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "EMAIL_URL is empty"):
            evaluate_settings(EMAIL_URL="")

    def test_malformed_query_names_the_variable(self):
        with self.assertRaisesMessage(ValueError, "EMAIL_URL"):
            evaluate_settings(EMAIL_URL="smtp://mail.example.com?timeout=10s")

    def test_no_email_setting_is_set(self):
        # Django 6.1 deprecates the EMAIL_* settings and refuses them next to MAILERS.
        self.assertEqual([name for name in evaluate_settings() if name.startswith("EMAIL_")], [])
