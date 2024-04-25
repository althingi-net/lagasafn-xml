import Levenshtein
import re
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from lagasafn.problems import ProblemHandler
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.webdriver import WebDriver


def remove_whitespace(s):
    """
    Remove all kinds of whitespace
    """
    return re.sub(r"\s+", "", s)


class WebTests(StaticLiveServerTestCase):
    # fixtures = ["user-data.json"]  # No database yet.

    def _get_law_links(self):
        self.get_if_needed(f"{self.live_server_url}/law/list/")

        xml_links = self.selenium.find_elements(By.CSS_SELECTOR, "a.law-link")
        self.assertTrue(len(xml_links) > 0, "Found no laws.")

        script = """
            const links = Array.from(document.querySelectorAll("a.law-link"));
            return links.map(link => ({
                href: window.location.origin + link.getAttribute('href'),
                identifier: link.getAttribute('data-identifier'),
                original_url: link.getAttribute('data-original-url')
            }));
        """
        law_links = self.selenium.execute_script(script)
        return law_links

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

    def get_if_needed(self, href):
        if self.selenium.current_url != href:
            self.selenium.get(href)

    def check_javascript(self, law_link):
        """
        Checks to see if the currently open page ran JavaScript without errors.
        """

        success = False

        self.get_if_needed(law_link["href"])

        try:
            self.selenium.find_element(By.ID, "law-javascript-success")
            self.problems.success(law_link["identifier"], "javascript")
            success = True

        except NoSuchElementException:

            # Retrieve the error message.
            body = self.selenium.find_element(By.CSS_SELECTOR, "body")
            message = body.get_attribute("js-error-message")

            self.problems.failure(law_link["identifier"], "javascript", message)

        return success

    def check_content(self, law_link):
        """
        Checks if locally rendered content is identical to remote content.
        """

        success = False

        self.get_if_needed(law_link["href"])

        # Get the text as rendered by our web application.
        local_text = remove_whitespace(
            self.selenium.find_element(By.CSS_SELECTOR, "law").text
        )

        # Get the official text.
        self.get_if_needed(f"{law_link['href']}cleaned/")

        remote_text = remove_whitespace(
            self.selenium.find_element(By.CSS_SELECTOR, "body").text
        )

        # Remove known garbage from remote text.
        garbage_denomenator = "Prentaítveimurdálkum."
        remote_text = remote_text[
            remote_text.find(garbage_denomenator) + len(garbage_denomenator) :
        ]

        if local_text == remote_text:
            self.problems.success(law_link["identifier"], "content")
            success = True
        else:
            ratio = Levenshtein.ratio(local_text, remote_text)
            self.problems.failure(
                law_link["identifier"], "content", f"Levenshtein ratio: {ratio:.8f}"
            )

        return success

    def test_rendering(self):

        law_links = self._get_law_links()

        # Tells if there are any errors in any law.
        has_errors = False

        for law_link in law_links:

            print("Testing %s..." % law_link["identifier"], end="", flush=False)

            # List of failures to be displayed in the log.
            failures = []

            if not self.check_javascript(law_link):
                failures.append("javascript")

            if not self.check_content(law_link):
                failures.append("content")

            if len(failures) == 0:
                print(" success")
            else:
                has_errors = True
                print(" failure: %s" % ", ".join(failures))

        self.assertFalse(has_errors, "Content mismatch detected.")
