from test_plus.test import TestCase


class SmokeTest(TestCase):
    def test_home_renders(self):
        self.get("/")
        self.assertResponseContains("Django + Tailwind + HTMX", html=False)

    def test_admin_login_renders(self):
        self.get_check_200("admin:login")
