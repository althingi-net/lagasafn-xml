import Levenshtein
import re
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from dotenv import load_dotenv
from lagasafn.problems import PROBLEM_TYPES
from lagasafn.problems import ProblemHandler
from os import environ
from os.path import exists
from rich import print
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver import ChromeOptions

# Load settings from environment variable file.
if exists(".env.tests"):
    load_dotenv(".env.tests")
else:
    load_dotenv(".env.tests.example")


def remove_whitespace(s):
    """
    Remove all kinds of whitespace
    """
    return re.sub(r"\s+", "", s)


class WebTests(StaticLiveServerTestCase):
    # fixtures = ["user-data.json"]  # No database yet.

    def _get_law_links(self):

        result = []

        self.get_if_needed(f"{self.live_server_url}/law/list/")

        # JavaScript is **way, way, way** faster then looking attributes up
        # using the Selenium API.
        script = """
            const links = Array.from(document.querySelectorAll("a.law-link"));
            return links.map(link => ({
                href: window.location.origin + link.getAttribute('href'),
                identifier: link.getAttribute('data-identifier'),
                original_url: link.getAttribute('data-original-url')
            }));
        """
        law_links = self.selenium.execute_script(script)

        requested = []
        env_test_laws = environ.get("TEST_LAWS")
        if env_test_laws:
            requested = env_test_laws.split(",")

        if len(requested) > 0:
            for law_link in law_links:
                if law_link["identifier"] in requested:
                    result.append(law_link)
                    requested.remove(law_link["identifier"])
        else:
            for law_link in law_links:
                result.append(law_link)

        if len(requested) > 0:
            raise Exception("Unknown laws: %s" % ", ".join(requested))

        return result

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.problems = ProblemHandler()

        chrome_options = ChromeOptions()
        chrome_options.add_argument("--headless")
        cls.selenium = webdriver.Chrome(options=chrome_options)

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

        self.get_if_needed(law_link["href"])

        try:
            self.selenium.find_element(By.ID, "law-javascript-success")
            message = ""
            success = 1.0

        except NoSuchElementException:
            # Retrieve the error message.
            body = self.selenium.find_element(By.CSS_SELECTOR, "body")
            message = body.get_attribute("js-error-message")
            success = 0.0

        progression = self.problems.report(law_link["identifier"], "javascript", success, message)

        return success, progression

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

        success = round(Levenshtein.ratio(local_text, remote_text), 8)

        progression = self.problems.report(law_link["identifier"], "content", success)

        return success, progression

    def test_rendering(self):

        law_links = self._get_law_links()

        # Tells if there are any errors in any law.
        has_errors = False

        for law_link in law_links:

            out_identifier = law_link["identifier"]
            while len(out_identifier) < 8:
                out_identifier = " %s" % out_identifier
            print("%s:" % out_identifier, end="", flush=True)

            for i, problem_type in enumerate(PROBLEM_TYPES):

                if i == 0:
                    print(" ", end="", flush=True)
                else:
                    print(", ", end="", flush=True)

                print("%s: " % problem_type, end="", flush=True)

                # Get the checking function for the problem type and make sure
                # that it is indeed a function.
                check_function = getattr(self, f"check_{problem_type}")
                if not callable(check_function):
                    raise Exception(
                        f"Check for '{problem_type}' problems unimplemented."
                    )

                # Actual checking.
                success, progression = check_function(law_link)

                out_success = format(success, ".8f")
                if success == 1.0:
                    out_success = "[green]%s[/green]" % out_success
                else:
                    out_success = "[red]%s[/red]" % out_success

                out_progression = format(progression, ".8f")
                if progression > 0.0:
                    out_progression = "[green]%s[/green]" % out_progression
                elif progression < 0.0:
                    out_progression = "[red]%s[/red]" % out_progression

                print("%s (%s)" % (out_success, out_progression), end="", flush=True)

                if not success:
                    has_errors = True

            print()

        self.assertFalse(has_errors, "Rendering errors detected.")
