import os
from lagasafn.constants import PROBLEMS_FILENAME
from lagasafn.utils import write_xml
from lxml import etree
from lxml.builder import E
from collections import OrderedDict

PROBLEM_TYPES = ["content", "javascript"]


class ProblemHandler:
    def __init__(self):
        # Create a basic `problems.xml` file if it doesn't exist.
        if not os.path.exists(PROBLEMS_FILENAME):
            root = E("problems")
            tree = etree.ElementTree(root)
            with open(PROBLEMS_FILENAME, "wb") as f:
                tree.write(f, pretty_print=True, xml_declaration=True, encoding="utf-8")

        self.xml = etree.parse(PROBLEMS_FILENAME).getroot()
        self.problems = {}

    def close(self):
        self.sort_by_content_distance()
        self.update_stats()
        write_xml(self.xml, PROBLEMS_FILENAME)

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
