from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.webdriver import WebDriver


class WebTests(StaticLiveServerTestCase):
    # fixtures = ["user-data.json"]  # No database yet.

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.selenium = WebDriver()
        cls.selenium.implicitly_wait(1)

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super().tearDownClass()

    def test_javascript(self):
        """
        Runs through laws displayed in the web app, opens them and sees if the
        initial JavaScript managed to complete without errors.
        """

        failed_hrefs = []

        self.selenium.get(f"{self.live_server_url}/law/list/")

        law_links = self.selenium.find_elements(By.CSS_SELECTOR, "a.law-link")
        self.assertTrue(len(law_links) > 0, "Found no laws.")

        hrefs = []
        for law_link in law_links:
            hrefs.append(law_link.get_attribute("href"))

        for href in hrefs:
            self.selenium.get(href)

            print("Finding success element %s..." % href, end="", flush=False)
            try:
                self.selenium.find_element(By.ID, "law-javascript-success")
                print(" success")
            except NoSuchElementException:
                failed_hrefs.append(href)
                print(" failed")

        if len(failed_hrefs) > 0:
            print("The following fails (%d) failed:", len(failed_hrefs))
            for failed_href in failed_hrefs:
                print(" - %s" % failed_href)

        self.assertTrue(len(failed_hrefs) == 0)
