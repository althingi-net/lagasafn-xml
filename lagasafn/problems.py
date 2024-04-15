import os
from lagasafn.settings import DATA_DIR
from lagasafn.utils import node_strip
from lagasafn.utils import write_xml
from lxml import etree
from lxml.builder import E

PROBLEMS_FILENAME = os.path.join(DATA_DIR, "xml", "problems.xml")


class ProblemHandler:
    def __init__(self):
        self.xml = node_strip(etree.parse(PROBLEMS_FILENAME).getroot())
        self.problems = {}

    def close(self):
        write_xml(self.xml, PROBLEMS_FILENAME)

    def get_law_entry(self, identifier: str):
        law_entries = self.xml.xpath("./problem-law-entry[@identifier='%s']" % identifier)
        if len(law_entries) == 0:
            law_entry = E("problem-law-entry", {"identifier": identifier})
            self.xml.append(law_entry)
            return law_entry
        else:
            return node_strip(law_entries[0])

    def get_status_entry(self, identifier: str, problem_type: str):
        law_entry = self.get_law_entry(identifier)
        status_entries = law_entry.xpath("./status[@type='%s']" % problem_type)
        if len(status_entries) == 0:
            status_entry = E("status", {"type": problem_type})
            law_entry.append(status_entry)
            return status_entry
        else:
            return node_strip(status_entries[0])

    def success(self, identifier: str, problem_type: str):
        status_entry = self.get_status_entry(identifier, problem_type)
        status_entry.attrib["success"] = "true"

    def failure(self, identifier: str, problem_type: str, message: str = ""):
        status_entry = self.get_status_entry(identifier, problem_type)

        if len(message):
            status_entry.attrib["message"] = message

        status_entry.attrib["success"] = "false"
