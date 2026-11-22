from tests.browser import BrowserTestCase


class HomePageTest(BrowserTestCase):
    def test_the_page_loads_htmx(self):
        self.page.goto(self.url("/"))
        self.assertTrue(self.page.evaluate("typeof htmx === 'object'"))
