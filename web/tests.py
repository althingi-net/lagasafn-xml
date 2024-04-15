from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from lagasafn.problems import ProblemHandler
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.webdriver import WebDriver


class WebTests(StaticLiveServerTestCase):
    # fixtures = ["user-data.json"]  # No database yet.

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.problems = ProblemHandler()

        cls.selenium = WebDriver()
        cls.selenium.implicitly_wait(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()

        cls.problems.close()

        super().tearDownClass()

    def test_javascript(self):
        """
        Runs through laws displayed in the web app, opens them and sees if the
        initial JavaScript managed to complete without errors.
        """

        self.selenium.get(f"{self.live_server_url}/law/list/")

        xml_links = self.selenium.find_elements(By.CSS_SELECTOR, "a.law-link")
        self.assertTrue(len(xml_links) > 0, "Found no laws.")

        law_links = []
        for xml_link in xml_links:
            law_links.append(
                {
                    "href": xml_link.get_attribute("href"),
                    "identifier": xml_link.get_attribute("data-identifier"),
                }
            )

        has_errors = False
        for law_link in law_links:
            self.selenium.get(law_link["href"])

            print(
                "Testing %s..." % law_link["identifier"], end="", flush=False
            )

            try:
                self.selenium.find_element(By.ID, "law-javascript-success")
                self.problems.success(law_link["identifier"], "javascript")
                print(" success")
            except NoSuchElementException:

                # Retrieve the error message.
                body = self.selenium.find_element(By.CSS_SELECTOR, "body")
                message = body.get_attribute("js-error-message")

                self.problems.failure(
                    law_link["identifier"],
                    "javascript",
                    message
                )

                print(" failure")
                has_errors = True

        self.assertFalse(has_errors, "JavaScript errors detected.")
