import os
from lagasafn.constants import PROBLEMS_FILENAME
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.utils import write_xml
from lxml import etree
from lxml.builder import E
from collections import OrderedDict

PROBLEM_TYPES = ["content", "javascript"]


class ProblemHandler:
    def __init__(self):
        # Create a basic `problems.xml` file if it doesn't exist.
        if not os.path.exists(PROBLEMS_FILENAME % CURRENT_PARLIAMENT_VERSION):
            root = E("problems")
            tree = etree.ElementTree(root)
            with open(PROBLEMS_FILENAME % CURRENT_PARLIAMENT_VERSION, "wb") as f:
                tree.write(f, pretty_print=True, xml_declaration=True, encoding="utf-8")

        self.xml = etree.parse(PROBLEMS_FILENAME % CURRENT_PARLIAMENT_VERSION).getroot()
        self.problems = {}

    def close(self):
        self.sort_by_content_distance()
        self.update_stats()
        write_xml(self.xml, PROBLEMS_FILENAME % CURRENT_PARLIAMENT_VERSION)

    def sort_by_content_distance(self):

        def sorter(element):
            content_element = element.find("status[@type='content']")
            if "distance" not in content_element.attrib:
                return -1

            return int(content_element.attrib["distance"])

        # Sort by reversed distance for `content`.
        sorted_entries = sorted(
            self.xml.findall("problem-law-entry"),
            key=sorter,
            reverse=True,
        )

        # Modify the XML accordingly, retaining the root element's attributes.
        old_attrib = dict(self.xml.attrib)
        self.xml.clear()
        self.xml.attrib.update(old_attrib)
        for sorted_entry in sorted_entries:
            self.xml.append(sorted_entry)

    def update_stats(self):
        # Ordered because we'll be using `git diff problems.xml` to monitor
        # bugfixing efforts.
        statistics = OrderedDict()
        for status in self.xml.findall("problem-law-entry/status"):
            status_type = status.attrib["type"]
            if "success" in status.attrib:
                success = float(status.attrib["success"]) == 1.0
            else:
                success = -1.0

            if status_type not in statistics:
                statistics[status_type] = {
                    "success": 0,
                    "failure": 0,
                }

            statistics[status_type]["success" if success else "failure"] += 1

        for status_type in statistics:
            successes = str(statistics[status_type]["success"])
            failures = str(statistics[status_type]["failure"])
            self.xml.attrib["stat-%s-success" % status_type] = successes
            self.xml.attrib["stat-%s-failure" % status_type] = failures

    def get_law_entry(self, identifier: str):
        law_entries = self.xml.xpath(
            "./problem-law-entry[@identifier='%s']" % identifier
        )
        if len(law_entries) == 0:
            law_entry = E("problem-law-entry", {"identifier": identifier})
            self.xml.append(law_entry)
            return law_entry
        else:
            return law_entries[0]

    def get_status_entry(self, identifier: str, problem_type: str):
        law_entry = self.get_law_entry(identifier)
        status_entries = law_entry.xpath("./status[@type='%s']" % problem_type)
        if len(status_entries) == 0:
            status_entry = E("status", {"type": problem_type})
            law_entry.append(status_entry)
            return status_entry
        else:
            return status_entries[0]

    def get_distance(self, identifier: str, problem_type: str):
        status_entry = self.get_status_entry(identifier, problem_type)
        print("Status entry fetch: %s" % status_entry)
        if "distance" in status_entry.attrib:
            return int(status_entry.attrib["distance"])
        else:
            return 0

    def report(
        self,
        identifier: str,
        problem_type: str,
        success: float,
        message: str = "",
        distance=0,
    ):
        status_entry = self.get_status_entry(identifier, problem_type)

        # Remember prior success for measuring progression.
        try:
            prior_success = float(status_entry.attrib["success"])
        except KeyError:
            prior_success = float("0.0")

        # From 0.0.. to 1.0.., indicating level of success from 0% to 100%.
        status_entry.attrib["success"] = f"{success:.8f}"
        if distance > 0 and success == 1.0:
            print("Inconsistency: distance > 0 and success == 1.0")
            status_entry.attrib["distance"] = "0"
        else:
            status_entry.attrib["distance"] = f"{distance}"

        if len(message):
            status_entry.attrib["message"] = message
        elif "message" in status_entry.attrib:
            status_entry.attrib.pop("message")

        # Return the prior success for comparison with new success.
        return round(prior_success, 8)


class AdvertProblemHandler:
    """
    Handler for problems.xml files in applied folders.
    Tracks advert application results and compares with next codex version.
    """

    def __init__(self, problems_filename: str):
        """
        Initialize AdvertProblemHandler.

        Args:
            problems_filename: Path to the problems.xml file in the applied folder.
        """
        self.problems_filename = problems_filename

        # Create a basic `problems.xml` file if it doesn't exist.
        if not os.path.exists(problems_filename):
            root = E("problems")
            tree = etree.ElementTree(root)
            with open(problems_filename, "wb") as f:
                tree.write(f, pretty_print=True, xml_declaration=True, encoding="utf-8")

        self.xml = etree.parse(problems_filename).getroot()
        self.problems = {}

    def close(self):
        self.sort_by_distance()
        self.update_stats()
        write_xml(self.xml, self.problems_filename)

    def sort_by_distance(self):
        """Sort entries by distance of 'content-stripped' status type (descending)."""

        def sorter(element):
            # Try to find content-stripped status first, then fall back to content
            status_element = element.find("status[@type='content-stripped']")
            if status_element is None:
                status_element = element.find("status[@type='content']")
            if status_element is None or "distance" not in status_element.attrib:
                return -1

            return int(status_element.attrib["distance"])

        # Sort by reversed distance (highest distance = worst matches first)
        sorted_entries = sorted(
            self.xml.findall("problem-law-entry"),
            key=sorter,
            reverse=True,
        )

        # Modify the XML accordingly, retaining the root element's attributes.
        old_attrib = dict(self.xml.attrib)
        self.xml.clear()
        self.xml.attrib.update(old_attrib)
        for sorted_entry in sorted_entries:
            self.xml.append(sorted_entry)

    def update_stats(self):
        """Update statistics for the problems.xml file."""
        statistics = OrderedDict()
        for status in self.xml.findall("problem-law-entry/status"):
            status_type = status.attrib["type"]
            if "success" in status.attrib:
                success = float(status.attrib["success"]) == 1.0
            else:
                success = -1.0

            if status_type not in statistics:
                statistics[status_type] = {
                    "success": 0,
                    "failure": 0,
                }

            statistics[status_type]["success" if success else "failure"] += 1

        for status_type in statistics:
            successes = str(statistics[status_type]["success"])
            failures = str(statistics[status_type]["failure"])
            self.xml.attrib["stat-%s-success" % status_type] = successes
            self.xml.attrib["stat-%s-failure" % status_type] = failures

    def get_law_entry(self, identifier: str):
        law_entries = self.xml.xpath(
            "./problem-law-entry[@identifier='%s']" % identifier
        )
        if len(law_entries) == 0:
            law_entry = E("problem-law-entry", {"identifier": identifier})
            self.xml.append(law_entry)
            return law_entry
        else:
            return law_entries[0]

    def get_status_entry(self, identifier: str, problem_type: str):
        law_entry = self.get_law_entry(identifier)
        status_entries = law_entry.xpath("./status[@type='%s']" % problem_type)
        if len(status_entries) == 0:
            status_entry = E("status", {"type": problem_type})
            law_entry.append(status_entry)
            return status_entry
        else:
            return status_entries[0]

    def set_adverts(
        self,
        identifier: str,
        adverts: list,
        advert_intents: dict = None,
        intent_distances: dict = None,
    ):
        """
        Set the adverts list for a law entry with their intents.

        Args:
            identifier: Law identifier (e.g., "88/1991")
            adverts: List of advert identifiers (e.g., ["63/2024", "64/2024"])
            advert_intents: Dictionary mapping advert identifiers to lists of intent info dicts
                           (e.g., {"63/2024": [{"action": "edit", "nr": 1, "action-xpath": "..."}, ...]})
            intent_distances: Dictionary mapping (advert_id, intent_nr, status_type) tuples to distances
                             (e.g., {("63/2024", 1, "content"): 5, ("63/2024", 1, "content-stripped"): 3})
        """
        law_entry = self.get_law_entry(identifier)

        # Remove existing adverts element if present
        existing_adverts = law_entry.find("adverts")
        if existing_adverts is not None:
            law_entry.remove(existing_adverts)

        # Add adverts element with child advert elements and their intents
        if adverts and len(adverts) > 0:
            adverts_elem = E("adverts")
            for advert_id in adverts:
                advert_elem = E("advert", {"identifier": advert_id})

                # Add intents
                if advert_intents and advert_id in advert_intents:
                    intents_elem = E("intents")
                    for intent_info in advert_intents[advert_id]:
                        action = intent_info.get("action")
                        intent_nr = intent_info.get("nr")

                        # Create simplified intent element with only action and nr
                        intent_elem = E("intent", {"action": action})
                        if intent_nr is not None:
                            intent_elem.set("nr", str(intent_nr))

                        # Add status elements for content and content-stripped
                        if intent_distances and intent_nr is not None:
                            for status_type in ["content", "content-stripped"]:
                                key = (advert_id, intent_nr, status_type)
                                if key in intent_distances:
                                    distance = intent_distances[key]
                                    if distance >= 0:
                                        status_elem = E("status", {"type": status_type})
                                        status_elem.set("distance", str(distance))

                                        # Get success ratio if available
                                        success_key = (
                                            advert_id,
                                            intent_nr,
                                            status_type,
                                            "success",
                                        )
                                        if success_key in intent_distances:
                                            success = intent_distances[success_key]
                                            status_elem.set("success", f"{success:.8f}")

                                        intent_elem.append(status_elem)

                        intents_elem.append(intent_elem)
                    advert_elem.append(intents_elem)

                adverts_elem.append(advert_elem)
            # Insert adverts before status elements
            status_elements = law_entry.findall("status")
            if status_elements:
                # Insert before first status element
                first_status_index = list(law_entry).index(status_elements[0])
                law_entry.insert(first_status_index, adverts_elem)
            else:
                # No status elements yet, just append
                law_entry.append(adverts_elem)

    def report(
        self,
        identifier: str,
        problem_type: str,
        success: float,
        distance=0,
    ):
        """
        Report a problem status.

        Args:
            identifier: Law identifier (e.g., "88/1991")
            problem_type: Type of problem (e.g., "file" or "stripped-law")
            success: Success ratio (0.0 to 1.0)
            distance: Levenshtein distance to next codex version
        """
        status_entry = self.get_status_entry(identifier, problem_type)

        # Remember prior success for measuring progression.
        try:
            prior_success = float(status_entry.attrib["success"])
        except KeyError:
            prior_success = float("0.0")

        # From 0.0.. to 1.0.., indicating level of success from 0% to 100%.
        status_entry.attrib["success"] = f"{success:.8f}"
        if distance > 0 and success == 1.0:
            print("Inconsistency: distance > 0 and success == 1.0")
            status_entry.attrib["distance"] = "0"
        else:
            status_entry.attrib["distance"] = f"{distance}"

        # Return the prior success for comparison with new success.
        return round(prior_success, 8)
