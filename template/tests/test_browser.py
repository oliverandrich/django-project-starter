from django.contrib.auth import get_user_model
from django.urls import reverse

from tests.browser import BrowserTestCase


class HomePageTest(BrowserTestCase):
    def test_the_page_loads_htmx(self):
        self.page.goto(self.url("/"))
        self.assertTrue(self.page.evaluate("typeof htmx === 'object'"))

    def test_htmx_requests_pass_the_csrf_check(self):
        self.page.goto(self.url("/"))
        with self.page.expect_response(self.url("/")) as response:
            self.page.evaluate("htmx.ajax('POST', '/', {swap: 'none'})")
        # 405 comes from the view, so CsrfViewMiddleware let the request through.
        self.assertEqual(response.value.status, 405)


class AdminPageTest(BrowserTestCase):
    def test_a_superuser_reaches_the_user_list(self):
        user_model = get_user_model()
        user_model.objects.create_superuser("admin", "admin@example.com", "a-long-password")
        self.page.goto(self.url(reverse("admin:login")))
        self.page.get_by_label("Username").fill("admin")
        self.page.get_by_label("Password").fill("a-long-password")
        self.page.get_by_role("button", name="Log in").click()
        self.page.wait_for_url(self.url(reverse("admin:index")))
        self.page.goto(self.url(reverse(f"admin:{user_model._meta.app_label}_user_changelist")))
        self.page.get_by_role("link", name="admin", exact=True).wait_for()
