import Levenshtein
import json
import re
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from dotenv import load_dotenv
from git import Repo
from lagasafn.problems import PROBLEM_TYPES
from lagasafn.problems import ProblemHandler
from os import environ
from os import path
from rich import print
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver import ChromeOptions

# Load settings from environment variable file.
if path.exists(".env.tests"):
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
                identifier: link.parentNode.parentNode.getAttribute('data-identifier'),
                original_url: link.getAttribute('data-original-url')
            }));
        """
        law_links = self.selenium.execute_script(script)

        requested = None
        env_test_laws = environ.get("TEST_LAWS")
        if env_test_laws == "modified":
            # Modified laws (according to `git`) are requested.
            requested = []

            git_repo_path = path.join(settings.BASE_DIR, "..")
            repo = Repo(git_repo_path)

            for item in repo.index.diff(None):

                # Only interested in stuff in `data/xml`.
                if not item.a_path.startswith("data/xml"):
                    continue

                filename = path.basename(item.a_path)
                if filename == "problems.xml":
                    # If the problem record is modified, the output is very
                    # misleading, so it's treated as an error.
                    raise Exception("Problem record (problems.xml) is modified.")
                elif filename.count(".") == 2:
                    # Looking for filenames like "1944.33.xml", i.e. laws.
                    law_year, law_nr, suffix = filename.split(".")
                    requested.append("%s/%s" % (law_nr, law_year))

        elif env_test_laws:
            # Specific laws are requested.
            requested = env_test_laws.split(",")

        # At this point, `requested` is None if all laws are to be processed,
        # but if some filtering has been requested, it will be a `list` with
        # the identifiers of those laws.

        if type(requested) is list:
            # The variable `requested` will be a `list` only when something
            # specific has been requested.
            for law_link in law_links:
                if law_link["identifier"] in requested:
                    result.append(law_link)
                    requested.remove(law_link["identifier"])
        else:
            # Otherwise, nothing specific has been requested, so we'll test
            # all of the laws.
            for law_link in law_links:
                result.append(law_link)

        if type(requested) is list and len(requested) > 0:
            # Laws that don't exist were requested.
            raise Exception("Unknown laws: %s" % ", ".join(requested))

        return result

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.problems = ProblemHandler()

        chrome_options = ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--remote-debugging-pipe")
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

        prior_success = self.problems.report(
            law_link["identifier"], "javascript", success, message
        )

        return success, prior_success

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
        self.get_if_needed(f"{law_link['href']}patched/")

        remote_text = remove_whitespace(
            self.selenium.find_element(By.CSS_SELECTOR, "body").text
        )

        # Remove known garbage from remote text.
        garbage_denomenator = "Prentaítveimurdálkum."
        remote_text = remote_text[
            remote_text.find(garbage_denomenator) + len(garbage_denomenator) :
        ]

        success = round(Levenshtein.ratio(local_text, remote_text), 8)
        distance = Levenshtein.distance(local_text, remote_text)

        # Record where to start looking for the problem if there is one.
        message = ""
        if success < 1.0:

            # No need to search beyond the shorter text.
            min_length = min(len(local_text), len(remote_text))

            # Scroll until we find a difference.
            difference_at = 0
            for i in range(min_length):
                if local_text[i] != remote_text[i]:
                    difference_at = i
                    break

            # If the difference doesn't occur within `local_text`, then the
            # problem is at its end.
            if difference_at == 0:
                difference_at = len(local_text)

            # We'll encode this as JSON.
            # NOTE: These texts are void of whitespace, because when evaluating
            # correctness, we have hitherto not cared about that.
            message_before = remote_text[difference_at - 50 : difference_at]
            message_after = remote_text[difference_at : difference_at + 50]
            if len(message_before) or len(message_after):
                message = "%s | %s" % (message_before, message_after)

        prior_success = self.problems.report(
            law_link["identifier"],
            "content",
            success,
            message=message,
            distance=distance,
        )

        return success, prior_success

    def test_rendering(self):

        law_links = self._get_law_links()

        # Aggregated results for this run.
        has_errors = False
        new_successes = 0
        new_failures = 0
        improvements = 0
        worsenings = 0

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
                success, prior_success = check_function(law_link)

                # Record new successes and new failures.
                if success == 1.0 and prior_success < 1.0:
                    new_successes += 1
                elif success < 1.0 and prior_success == 1.0:
                    new_failures += 1

                # Record improvements and worsenings.
                if success > prior_success:
                    improvements += 1
                elif success < prior_success:
                    worsenings += 1

                # Format success output.
                out_success = format(success, ".8f")
                if success == 1.0:
                    out_success = "[green]%s[/green]" % out_success
                else:
                    out_success = "[red]%s[/red]" % out_success

                # Format prior success output.
                out_prior_success = format(prior_success, ".8f")
                if prior_success == 1.0:
                    out_prior_success = "[green]%s[/green]" % out_prior_success
                else:
                    out_prior_success = "[red]%s[/red]" % out_prior_success

                # Calculate and format progression.
                progression = success - prior_success
                out_progression = format(progression, ".8f")
                if progression > 0.0:
                    out_progression = "[green]+%s[/green]" % out_progression
                elif progression < 0.0:
                    # NOTE: The "-" sign will be automatically included.
                    out_progression = "[red]%s[/red]" % out_progression
                else:
                    # Space added to pad for the +/- signs added elsewhere.
                    out_progression = " %s" % out_progression

                print(
                    "%s, %s (%s)" % (out_success, out_prior_success, out_progression),
                    end="",
                    flush=True,
                )

                if not success:
                    has_errors = True

            print()

        # Print aggregates results from run.
        print("------------------")
        print("New successes : %d" % new_successes)
        print("New failures  : %d" % new_failures)
        print("------------------")
        print("Improvements  : %d" % improvements)
        print("Worsenings    : %d" % worsenings)
        print("------------------")

        self.assertFalse(has_errors, "Rendering errors detected.")
