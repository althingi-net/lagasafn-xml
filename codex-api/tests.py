import Levenshtein
import os
import re
from collections import defaultdict
from copy import deepcopy
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import TestCase
from dotenv import load_dotenv
from git import Repo
from lagasafn.constants import XML_BASE_DIR
from lagasafn.models.advert import Advert, AdvertManager
from lagasafn.models.law import Law, LawManager
from lagasafn.problems import PROBLEM_TYPES
from lagasafn.problems import AdvertProblemHandler
from lagasafn.problems import ProblemHandler
from lagasafn.utils import get_all_text
from lxml import etree
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


def strip_minister_clause_and_footnotes(xml_root):
    """Create a copy of XML with minister-clause and footnotes removed."""
    stripped_xml = deepcopy(xml_root)

    # Remove minister-clause
    minister_clause = stripped_xml.find("minister-clause")
    if minister_clause is not None:
        stripped_xml.remove(minister_clause)

    # Remove all footnotes recursively
    for footnote in stripped_xml.findall(".//footnote"):
        parent = footnote.getparent()
        if parent is not None:
            parent.remove(footnote)

    return stripped_xml


class AdvertApplyingTests(TestCase):
    """
    Test class for validating applied adverts.
    Tests compare applied law content with the next codex version
    and generate problems.xml files in the applied folders.
    """

    def test_advert_applying(self):
        """
        Test applied adverts by comparing them with the next codex version.
        Creates problems.xml in each codex version's applied folder.
        """
        codex_versions = LawManager.codex_versions()
        for codex_version in codex_versions:
            self._process_codex_version(codex_version)

    def _process_codex_version(self, codex_version):
        """Process a single codex version."""
        applied_dir = path.join(XML_BASE_DIR, codex_version, "applied")

        # Skip if applied directory doesn't exist
        if not os.path.exists(applied_dir) or not os.path.isdir(applied_dir):
            return

        print(f"\nProcessing codex version: {codex_version}")

        # Parse applied files
        law_applied_files = self._parse_applied_files(applied_dir, codex_version)
        if not law_applied_files:
            print(f"  No valid applied files found in {codex_version}")
            return

        # Create AdvertProblemHandler for this codex version's applied folder
        problems_filename = path.join(applied_dir, "problems.xml")
        problems = AdvertProblemHandler(problems_filename=problems_filename)

        # Get next codex version
        next_codex_version = LawManager.get_next_codex_version(codex_version)

        # Process each law
        for law_identifier, applied_info_list in law_applied_files.items():
            self._process_law(
                law_identifier,
                applied_info_list,
                problems,
                next_codex_version,
            )

        # Save the problems.xml file
        problems.close()
        print(f"  Created problems.xml for {codex_version}")

    def _parse_applied_files(self, applied_dir, codex_version):
        """
        Parse applied files and group by law identifier.
        Returns a dictionary mapping law identifiers to lists of applied file info.
        """
        # Find all applied files
        applied_files = [
            f
            for f in os.listdir(applied_dir)
            if f.endswith(".xml") and f != "problems.xml"
        ]

        if not applied_files:
            print(f"  No applied files found")
            return {}

        # Group applied files by law identifier
        # Filename format: {year}.{nr}-{enact_date}.xml
        law_applied_files = defaultdict(list)

        for filename in applied_files:
            # Parse filename: e.g., "1991.88-2024-07-12.xml"
            # Remove .xml extension
            base_name = filename[:-4]
            # Split by '-' to separate law and enact date parts
            parts = base_name.split("-", 1)
            if len(parts) != 2:
                print(f"  Warning: Could not parse filename: {filename}")
                continue

            law_part = parts[0]  # e.g., "1991.88"
            enact_date = parts[1]  # e.g., "2024-07-12"

            # Parse law identifier
            law_year, law_nr = law_part.split(".")
            law_identifier = f"{law_nr}/{law_year}"

            # Find adverts that match this enact date
            matching_adverts = self._find_adverts_by_enact_date(
                law_identifier, codex_version, enact_date
            )

            applied_file_path = path.join(applied_dir, filename)
            law_applied_files[law_identifier].append(
                {
                    "enact_date": enact_date,
                    "advert_identifiers": matching_adverts,
                    "file_path": applied_file_path,
                }
            )

        return law_applied_files

    def _find_adverts_by_enact_date(self, law_identifier, codex_version, enact_date):
        """
        Find adverts that affect a law and have an enact intent with the given timing.
        Returns a list of advert identifiers.
        """
        # Parse law identifier to get nr and year
        law_nr, law_year = law_identifier.split("/")

        # Get all adverts that affect this law
        adverts = AdvertManager.by_affected_law(codex_version, law_nr, int(law_year))

        matching_adverts = []
        for advert_entry in adverts:
            # Convert AdvertEntry to Advert to access xml() method
            advert = Advert(advert_entry.identifier)
            advert_xml = advert.xml()
            # Find enact intents with matching timing
            for intent in advert_xml.findall(".//intent"):
                if intent.get("action") == "enact":
                    intent_timing = intent.get("timing")
                    if intent_timing == enact_date:
                        matching_adverts.append(advert_entry.identifier)
                        break
        return matching_adverts

    def _extract_intents_from_adverts(self, applied_info_list, law_identifier):
        """
        Extract intents from adverts that target a specific law.
        Returns a dictionary mapping advert identifiers to lists of intent info.
        """
        advert_intents = {}
        for info in applied_info_list:
            for advert_id in info["advert_identifiers"]:
                advert = Advert(advert_id)
                advert_xml = advert.xml()
                # Find all intents for this law in the advert
                intents = []
                intent_nr = 1
                for intent in advert_xml.findall(".//intent"):
                    # Check if this intent targets the current law
                    action = intent.get("action")
                    should_include = False

                    if action == "repeal":
                        if intent.get("action-identifier") == law_identifier:
                            should_include = True
                    elif action == "enact":
                        # Enact intents apply to all laws in the advert
                        should_include = True
                    else:
                        # Other actions use action-law-nr and action-law-year
                        law_nr = intent.get("action-law-nr")
                        law_year = intent.get("action-law-year")
                        if law_nr and law_year:
                            intent_law_id = f"{law_nr}/{law_year}"
                            if intent_law_id == law_identifier:
                                should_include = True

                    if should_include:
                        # Store action, nr, and action-xpath (xpath needed for distance calculation)
                        intent_info = {
                            "action": action,
                            "nr": intent_nr,
                            "action-xpath": intent.get("action-xpath", ""),
                        }
                        intents.append(intent_info)
                        intent_nr += 1

                if intents:
                    advert_intents[advert_id] = intents

        return advert_intents

    def _process_law(
        self, law_identifier, applied_info_list, problems, next_codex_version
    ):
        """Process a single law: compare with next version and report results."""
        # Collect all advert identifiers
        all_advert_identifiers = set()
        for info in applied_info_list:
            all_advert_identifiers.update(info["advert_identifiers"])

        print(
            f"  {law_identifier}: {len(applied_info_list)} applied files, {len(all_advert_identifiers)} adverts"
        )

        # Extract intents from adverts
        advert_intents = self._extract_intents_from_adverts(
            applied_info_list, law_identifier
        )

        # Get the most recent applied file for this law (sort by enact_date)
        applied_info_list.sort(key=lambda x: x["enact_date"], reverse=True)
        latest_applied_file = applied_info_list[0]["file_path"]

        # Load the applied law XML
        applied_law_xml = self._load_applied_law(latest_applied_file, law_identifier)
        if applied_law_xml is None:
            self._handle_error_case(
                problems, law_identifier, applied_info_list, advert_intents, 0.0, 0
            )
            return

        # Compare with next codex version if available
        if next_codex_version is None:
            print(f"    No next codex version available")
            self._handle_error_case(
                problems, law_identifier, applied_info_list, advert_intents, 1.0, 0
            )
            return

        # Load the law from next codex version
        next_law_xml = self._load_next_law(law_identifier, next_codex_version)
        if next_law_xml is None:
            self._handle_error_case(
                problems, law_identifier, applied_info_list, advert_intents, 0.0, 0
            )
            return

        # Compare law with next version
        comparison_results = self._compare_law_with_next_version(
            applied_law_xml, next_law_xml
        )

        # Calculate distances for each intent
        intent_distances = self._calculate_intent_distances(
            advert_intents, applied_law_xml, next_law_xml
        )

        # Report results
        self._report_law_results(
            problems,
            law_identifier,
            applied_info_list,
            advert_intents,
            intent_distances,
            comparison_results,
        )

    def _load_applied_law(self, applied_file_path, law_identifier):
        """Load applied law XML from file."""
        try:
            return etree.parse(applied_file_path).getroot()
        except Exception as e:
            print(f"    Error loading applied law {law_identifier}: {e}")
            return None

    def _load_next_law(self, law_identifier, next_codex_version):
        """Load law from next codex version."""
        try:
            next_law = Law(law_identifier, next_codex_version)
            return next_law.xml().getroot()
        except Exception as e:
            print(f"    Error loading next codex version law: {e}")
            return None

    def _compare_law_with_next_version(self, applied_law_xml, next_law_xml):
        """
        Compare applied law with next codex version.
        Returns a dictionary with comparison results.
        """
        # Get text for whole file comparison
        applied_text = remove_whitespace(get_all_text(applied_law_xml))

        # Get text for content-only comparison (without minister-clause and footnotes)
        applied_law_xml_stripped = strip_minister_clause_and_footnotes(applied_law_xml)
        applied_text_content = remove_whitespace(get_all_text(applied_law_xml_stripped))

        # Get text for whole file comparison
        next_text = remove_whitespace(get_all_text(next_law_xml))

        # Get text for content-only comparison (without minister-clause and footnotes)
        next_law_xml_stripped = strip_minister_clause_and_footnotes(next_law_xml)
        next_text_content = remove_whitespace(get_all_text(next_law_xml_stripped))

        # Calculate distance for whole file
        success = round(Levenshtein.ratio(applied_text, next_text), 8)
        distance = Levenshtein.distance(applied_text, next_text)

        # Calculate distance for content-only (without minister-clause and footnotes)
        success_content = round(
            Levenshtein.ratio(applied_text_content, next_text_content), 8
        )
        distance_content = Levenshtein.distance(applied_text_content, next_text_content)

        return {
            "success": success,
            "distance": distance,
            "success_content": success_content,
            "distance_content": distance_content,
        }

    def _calculate_intent_distances(
        self, advert_intents, applied_law_xml, next_law_xml
    ):
        """
        Calculate metrics for each intent.
        Returns a dictionary mapping (advert_id, intent_nr, metric_type) to values.
        """
        intent_distances = {}
        if not advert_intents:
            return intent_distances

        for advert_id, intents in advert_intents.items():
            for intent_info in intents:
                intent_nr = intent_info.get("nr")
                action_xpath = intent_info.get("action-xpath", "")
                action = intent_info.get("action", "")

                if intent_nr is None or not action_xpath:
                    # Skip intents without nr or xpath
                    continue

                # Find the element in applied law XML
                applied_elements = applied_law_xml.xpath(action_xpath)
                exists_applied = len(applied_elements) > 0
                intent_distances[(advert_id, intent_nr, "exists-applied")] = (
                    exists_applied
                )

                if not exists_applied:
                    # Element doesn't exist in applied version
                    continue

                applied_element = applied_elements[0]

                # Find the element in next codex version XML
                next_elements = next_law_xml.xpath(action_xpath)
                exists_next = len(next_elements) > 0
                intent_distances[(advert_id, intent_nr, "exists-next")] = exists_next

                # For delete actions, success means element should NOT exist
                if action == "delete":
                    intent_distances[(advert_id, intent_nr, "delete-success")] = (
                        not exists_next
                    )
                    continue

                if not exists_next:
                    # Element doesn't exist in next version (but should for non-delete actions)
                    intent_distances[(advert_id, intent_nr, "content")] = -1
                    intent_distances[(advert_id, intent_nr, "content-stripped")] = -1
                    continue

                next_element = next_elements[0]

                # Element Type Match
                tag_match = applied_element.tag == next_element.tag
                intent_distances[(advert_id, intent_nr, "tag-match")] = tag_match

                # Content Similarity
                applied_element_text = remove_whitespace(get_all_text(applied_element))
                applied_element_stripped = strip_minister_clause_and_footnotes(
                    applied_element
                )
                applied_element_text_stripped = remove_whitespace(
                    get_all_text(applied_element_stripped)
                )

                next_element_text = remove_whitespace(get_all_text(next_element))
                next_element_stripped = strip_minister_clause_and_footnotes(
                    next_element
                )
                next_element_text_stripped = remove_whitespace(
                    get_all_text(next_element_stripped)
                )

                # Calculate distances and success ratios for both content and content-stripped
                intent_distance_content = Levenshtein.distance(
                    applied_element_text, next_element_text
                )
                intent_success_content = round(
                    Levenshtein.ratio(applied_element_text, next_element_text), 8
                )

                intent_distance_stripped = Levenshtein.distance(
                    applied_element_text_stripped, next_element_text_stripped
                )
                intent_success_stripped = round(
                    Levenshtein.ratio(
                        applied_element_text_stripped, next_element_text_stripped
                    ),
                    8,
                )

                intent_distances[(advert_id, intent_nr, "content")] = (
                    intent_distance_content
                )
                intent_distances[(advert_id, intent_nr, "content", "success")] = (
                    intent_success_content
                )
                intent_distances[(advert_id, intent_nr, "content-stripped")] = (
                    intent_distance_stripped
                )
                intent_distances[
                    (advert_id, intent_nr, "content-stripped", "success")
                ] = intent_success_stripped

                # Structural Similarity
                applied_children = [
                    c for c in applied_element if isinstance(c.tag, str)
                ]
                next_children = [c for c in next_element if isinstance(c.tag, str)]
                applied_children_count = len(applied_children)
                next_children_count = len(next_children)
                intent_distances[(advert_id, intent_nr, "children-count-applied")] = (
                    applied_children_count
                )
                intent_distances[(advert_id, intent_nr, "children-count-next")] = (
                    next_children_count
                )
                intent_distances[(advert_id, intent_nr, "children-count-match")] = (
                    applied_children_count == next_children_count
                )

                # Key attribute matching
                key_attributes = [
                    "nr",
                    "ultimate-nr",
                    "sub-paragraph-nr",
                    "chapter-type",
                ]
                attribute_matches = {}
                for attr in key_attributes:
                    applied_val = applied_element.get(attr)
                    next_val = next_element.get(attr)
                    if applied_val is not None or next_val is not None:
                        attribute_matches[attr] = applied_val == next_val

                if attribute_matches:
                    intent_distances[
                        (advert_id, intent_nr, "attribute-match-ratio")
                    ] = round(
                        sum(attribute_matches.values()) / len(attribute_matches), 8
                    )
                else:
                    intent_distances[
                        (advert_id, intent_nr, "attribute-match-ratio")
                    ] = 1.0

                # Position Accuracy
                applied_parent = applied_element.getparent()
                next_parent = next_element.getparent()
                if applied_parent is not None and next_parent is not None:
                    applied_siblings = [
                        e for e in applied_parent if e.tag == applied_element.tag
                    ]
                    next_siblings = [
                        e for e in next_parent if e.tag == next_element.tag
                    ]
                    applied_position = (
                        applied_siblings.index(applied_element)
                        if applied_element in applied_siblings
                        else -1
                    )
                    next_position = (
                        next_siblings.index(next_element)
                        if next_element in next_siblings
                        else -1
                    )
                    intent_distances[(advert_id, intent_nr, "position-applied")] = (
                        applied_position
                    )
                    intent_distances[(advert_id, intent_nr, "position-next")] = (
                        next_position
                    )
                    intent_distances[(advert_id, intent_nr, "position-match")] = (
                        applied_position == next_position and applied_position >= 0
                    )

                # Context Similarity (Parent Element)
                if applied_parent is not None and next_parent is not None:
                    parent_tag_match = applied_parent.tag == next_parent.tag
                    intent_distances[(advert_id, intent_nr, "parent-tag-match")] = (
                        parent_tag_match
                    )

                    # Parent content similarity
                    applied_parent_text = remove_whitespace(
                        get_all_text(applied_parent)
                    )
                    next_parent_text = remove_whitespace(get_all_text(next_parent))
                    parent_similarity = round(
                        Levenshtein.ratio(applied_parent_text, next_parent_text), 8
                    )
                    intent_distances[(advert_id, intent_nr, "parent-similarity")] = (
                        parent_similarity
                    )

                # Overall Intent Success Score
                children_count_match = intent_distances.get(
                    (advert_id, intent_nr, "children-count-match"), False
                )
                position_match = intent_distances.get(
                    (advert_id, intent_nr, "position-match"), False
                )

                overall_success = (
                    tag_match
                    and intent_success_stripped > 0.95
                    and children_count_match
                    and position_match
                )
                intent_distances[(advert_id, intent_nr, "overall-success")] = (
                    overall_success
                )

        return intent_distances

    def _report_law_results(
        self,
        problems,
        law_identifier,
        applied_info_list,
        advert_intents,
        intent_distances,
        comparison_results,
    ):
        """Report comparison results to the problems handler."""
        # Collect advert identifiers from all applied files
        advert_set = set()
        for info in applied_info_list:
            advert_set.update(info["advert_identifiers"])
        advert_list = list(advert_set)

        problems.set_adverts(
            law_identifier,
            advert_list,
            advert_intents=advert_intents,
            intent_distances=intent_distances,
        )

        # Report whole file comparison
        problems.report(
            law_identifier,
            "content",
            comparison_results["success"],
            distance=comparison_results["distance"],
        )

        # Report content-only comparison
        problems.report(
            law_identifier,
            "content-stripped",
            comparison_results["success_content"],
            distance=comparison_results["distance_content"],
        )

        # Calculate intent-level summary statistics
        intent_count = sum(len(intents) for intents in advert_intents.values())
        successful_intents = 0
        failed_intents = 0
        for advert_id, intents in advert_intents.items():
            for intent_info in intents:
                intent_nr = intent_info.get("nr")
                if intent_nr is None:
                    continue
                overall_success = intent_distances.get(
                    (advert_id, intent_nr, "overall-success"), 0.0
                )
                if overall_success >= 0.8:
                    successful_intents += 1
                else:
                    failed_intents += 1

        print(
            f"    Success (content): {comparison_results['success']:.8f}, "
            f"Distance: {comparison_results['distance']}, "
            f"Success (content-stripped): {comparison_results['success_content']:.8f}, "
            f"Distance: {comparison_results['distance_content']}, "
            f"Adverts: {len(applied_info_list)}, "
            f"Intents: {intent_count} (successful: {successful_intents} failed: {failed_intents})"
        )

    def _handle_error_case(
        self,
        problems,
        law_identifier,
        applied_info_list,
        advert_intents,
        success,
        distance,
    ):
        """Handle error cases with consistent reporting."""
        # Collect advert identifiers from all applied files
        advert_set = set()
        for info in applied_info_list:
            advert_set.update(info["advert_identifiers"])
        advert_list = list(advert_set)

        problems.set_adverts(
            law_identifier,
            advert_list,
            advert_intents=advert_intents,
            intent_distances={},
        )
        problems.report(law_identifier, "content", success, distance=distance)
        problems.report(law_identifier, "content-stripped", success, distance=distance)
