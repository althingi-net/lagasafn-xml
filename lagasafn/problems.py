import os
from lagasafn.settings import DATA_DIR
from lagasafn.utils import write_xml
from lxml import etree
from lxml.builder import E
from collections import OrderedDict

PROBLEM_TYPES = ["content", "javascript"]
PROBLEMS_FILENAME = os.path.join(DATA_DIR, "xml", "problems.xml")


class ProblemHandler:
    def __init__(self):
        self.xml = etree.parse(PROBLEMS_FILENAME).getroot()
        self.problems = {}

    def close(self):
        self.update_stats()
        write_xml(self.xml, PROBLEMS_FILENAME)

    def update_stats(self):
        # Ordered because we'll be using `git diff problems.xml` to monitor
        # bugfixing efforts.
        statistics = OrderedDict()
        for status in self.xml.findall("problem-law-entry/status"):
            status_type = status.attrib["type"]
            success = float(status.attrib["success"]) == 1.0

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
        prior_success = float(status_entry.attrib["success"])

        # From 0.0.. to 1.0.., indicating level of success from 0% to 100%.
        status_entry.attrib["success"] = f"{success:.8f}"
        if distance > 0:
            status_entry.attrib["distance"] = f"{distance}"

        if len(message):
            status_entry.attrib["message"] = message
        elif "message" in status_entry.attrib:
            status_entry.attrib.pop("message")

        # Return the prior success for comparison with new success.
        return round(prior_success, 8)
