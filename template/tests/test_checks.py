from contextlib import contextmanager
from unittest import mock

from django.core import checks
from django.core.signals import setting_changed
from django.test import SimpleTestCase, override_settings
from django.utils.module_loading import import_string

from tests.utils import PACKAGE

check_secret_key = import_string(f"{PACKAGE}.checks.check_secret_key")
check_allowed_hosts = import_string(f"{PACKAGE}.checks.check_allowed_hosts")


def ids(messages: list[checks.CheckMessage]) -> list[str | None]:
    return [message.id for message in messages]


@contextmanager
def empty_secret_key(*, debug: bool):
    # A setting_changed receiver, such as a login library's, may refuse an empty key.
    # All receivers stay silent here; the checks read the settings directly.
    with (
        mock.patch.object(setting_changed, "receivers", []),
        override_settings(DEBUG=debug, SECRET_KEY=""),
    ):
        yield


class SecretKeyCheckTest(SimpleTestCase):
    def test_an_empty_key_outside_debug_is_an_error(self):
        # Django refuses to return an empty SECRET_KEY; the check must not raise with it.
        with empty_secret_key(debug=False):
            self.assertEqual(ids(check_secret_key(None)), ["settings.E001"])

    @override_settings(DEBUG=False, SECRET_KEY="a-real-key")
    def test_a_key_passes(self):
        self.assertEqual(check_secret_key(None), [])

    def test_debug_needs_no_key(self):
        with empty_secret_key(debug=True):
            self.assertEqual(check_secret_key(None), [])


class AllowedHostsCheckTest(SimpleTestCase):
    @override_settings(DEBUG=False, ALLOWED_HOSTS=[])
    def test_no_hosts_outside_debug_is_an_error(self):
        self.assertEqual(ids(check_allowed_hosts(None)), ["settings.E002"])

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["example.com"])
    def test_a_host_passes(self):
        self.assertEqual(check_allowed_hosts(None), [])

    @override_settings(DEBUG=True, ALLOWED_HOSTS=[])
    def test_debug_needs_no_hosts(self):
        self.assertEqual(check_allowed_hosts(None), [])


class RegistrationTest(SimpleTestCase):
    def test_the_secret_key_check_runs_with_every_command(self):
        registered = checks.registry.registry.get_checks(include_deployment_checks=False)
        self.assertIn(check_secret_key, registered)

    def test_the_allowed_hosts_check_runs_with_check_deploy_only(self):
        # The worker and the scheduler serve no HTTP.
        registry = checks.registry.registry
        self.assertIn(check_allowed_hosts, registry.get_checks(include_deployment_checks=True))
        self.assertNotIn(check_allowed_hosts, registry.get_checks(include_deployment_checks=False))
