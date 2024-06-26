"""
The purpose of these models is to return the XML data in a form that is
suitable for JSON output or for use in a template. In essence, to alleviate
XML work from other parts of this system, or any other system communicating
with this one.
"""

import os
import re
from django.conf import settings
from lagasafn.problems import PROBLEM_TYPES
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.utils import traditionalize_law_nr
from law.exceptions import LawException
from lxml import etree


class LawManager:
    @staticmethod
    def index():
        # FIXME: This XML should be automatically converted to JSON using
        # some 3rd party library, instead of being converted from one ad-hoc
        # format to another ad-hoc format here.

        # Return variables.
        stats = {}
        laws = []

        # Collect known problems to mix with the index.
        # A dictionary (map) will be generated with the law's identifier as a
        # key, which can then be quickly looked up when we iterate through the
        # index below.
        problem_map = {}
        problems = etree.parse(
            os.path.join(settings.DATA_DIR, "problems.xml")
        ).getroot()
        for problem_law_entry in problems.findall("problem-law-entry"):
            statuses = {}
            for status_node in problem_law_entry.findall("status"):
                success = status_node.attrib["success"]
                message = (
                    status_node.attrib["message"]
                    if "message" in status_node.attrib
                    else None
                )
                statuses[status_node.attrib["type"]] = {
                    "success": float(success),
                    "message": message,
                }
            problem_map[problem_law_entry.attrib["identifier"]] = statuses

        # Read and parse the index
        index = etree.parse(os.path.join(settings.DATA_DIR, "index.xml")).getroot()

        # Gather statistics.
        for node_stat in index.findall("stats/"):
            # Dashes are preferred in XML but underscores are needed in
            # templates.
            var_name = node_stat.tag.replace("-", "_")

            try:
                # Convert the value to integer if it's an integer.
                var_value = int(node_stat.text)
            except ValueError:
                # Whatever. It's something else.
                var_value = node_stat.text

            stats[var_name] = var_value

        # Gather the laws in the index.
        for node_law_entry in index.findall("law-entries/law-entry"):
            if node_law_entry.find("meta/is-empty").text == "true":
                continue

            problems = {}
            if node_law_entry.attrib["identifier"] in problem_map:
                problems = problem_map[node_law_entry.attrib["identifier"]]

            laws.append(LawEntry(node_law_entry, problems))

        return stats, laws


class LawEntry:
    """
    Intermediary model for a legal entry in the index.
    """

    def __init__(self, node_law_entry, problems):
        self.identifier = node_law_entry.attrib["identifier"]
        self.name = node_law_entry.find("name").text
        self.chapter_count = int(node_law_entry.find("meta/chapter-count").text)
        self.art_count = node_law_entry.find("meta/art-count").text

        self.nr, self.year = self.identifier.split("/")

        self.problems = problems

    def original_url(self):
        """
        Reconstructs the URL to the original HTML on Althingi's website.
        """
        original_law_filename = "%s%s.html" % (
            str(self.year),
            traditionalize_law_nr(self.nr),
        )

        return "https://www.althingi.is/lagas/%s/%s" % (
            CURRENT_PARLIAMENT_VERSION,
            original_law_filename,
        )

    def status(self):
        """
        Determines the status of the law, judging by known problem types.
        """
        problems_accounted_for = True
        for problem_type in PROBLEM_TYPES:
            if problem_type not in self.problems:
                problems_accounted_for = False

        if problems_accounted_for:
            all_ok = all(self.problems[p]["success"] == 1.0 for p in self.problems)
        else:
            all_ok = None

        return all_ok

    def __str__(self):
        return self.identifier


class Law(LawEntry):

    def __init__(self, identifier):
        self.identifier = identifier

        # Private containers, essentially for caching.
        self._xml = None
        self._name = ""
        self._xml_text = ""
        self._html_text = ""
        self._chapters = []
        self._articles = []

        self.nr, self.year = self.identifier.split("/")

        if not os.path.isfile(self.path()):
            raise LawException("Could not find law '%s'" % self.identifier)

    @staticmethod
    def _make_art(art):
        """
        Centralized function for making an `art` in the specific context of
        this model, from XML data.
        """
        _art = {
            "nr": art.attrib["nr"],
            "nr_title": art.find("nr-title").text,
        }

        # Add name if it exists.
        art_name = art.find("name")
        if art_name is not None:
            _art["name"] = art_name.text

        return _art

    def name(self):
        if len(self._name):
            return self._name

        # Has its own cache mechanism, so this is fast.
        xml = self.xml()

        self._name = xml.find("name").text

        return self._name

    def chapters(self):
        if len(self._chapters):
            return self._chapters

        xml = self.xml()

        for chapter in xml.findall("chapter"):
            _chapter = {
                "nr": chapter.attrib["nr"],
                "articles": [],
            }

            # Add nr-title if it exists.
            nr_title = chapter.find("nr-title")
            if nr_title is not None:
                _chapter["nr_title"] = nr_title.text

            # Add name if it exists.
            name = chapter.find("name")
            if name is not None:
                _chapter["name"] = name.text

            # Add articles.name
            for art in chapter.findall("art"):
                _art = Law._make_art(art)
                _chapter["articles"].append(_art)

            self._chapters.append(_chapter)

        return self._chapters

    def articles(self):
        if len(self._articles):
            return self._articles

        xml = self.xml()

        for art in xml.findall("art"):
            _art = Law._make_art(art)
            self._articles.append(_art)

        return self._articles

    def path(self):
        return os.path.join(settings.DATA_DIR, f"{self.year}.{self.nr}.xml")

    def xml(self):
        """
        Returns the law in XML object form.
        """
        if self._xml is None:
            self._xml = etree.parse(self.path())

        return self._xml

    def xml_text(self):
        """
        Returns the law in XML text form.
        """

        # Just return the content if we already have it.
        if len(self._xml_text) > 0:
            return self._xml_text

        # Open and load the XML content.
        with open(self.path()) as f:
            self._xml_text = f.read()

        return self._xml_text

    def html_text(self):
        """
        Returns the law in HTML text form.
        """

        # Just return the content if we already have it.
        if len(self._html_text) > 0:
            return self._html_text

        # Make sure we have the XML.
        xml_text = self.xml_text()

        # Turn the XML into HTML.
        # FIXME: This could use some explaining. There is a difference between
        # XML and HTML, but it's not obvious from reading this.
        e = re.compile(r"<([a-z\-]+)( ?)([^>]*)\/>")
        result = e.sub(r"<\1\2\3></\1>", xml_text)
        result = result.replace('<?xml version="1.0" encoding="utf-8"?>', "").strip()

        # Assigned separately so that we never have half-completed conversion
        # stored. More principle than practice.
        self._html_text = result

        return self._html_text

    def editor_url(self):
        return settings.EDITOR_URL % (self.year, self.nr)

    def __str__(self):
        return self.identifier
