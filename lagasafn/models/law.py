"""
The purpose of these models is to return the XML data in a form that is
suitable for JSON output or for use in a template. In essence, to alleviate
XML work from other parts of this system, or any other system communicating
with this one.
"""

import os
import re
import requests
from datetime import datetime
from django.conf import settings
from django.utils.html import strip_tags
from functools import cache
from importlib import import_module
from lagasafn.constants import PROBLEMS_FILENAME
from lagasafn.constants import CURRENT_PARLIAMENT_VERSION
from lagasafn.constants import XML_BASE_DIR
from lagasafn.constants import XML_INDEX_FILENAME
from lagasafn.constants import XML_FILENAME
from lagasafn.constants import XML_REFERENCES_FILENAME
from lagasafn.exceptions import LawException
from lagasafn.exceptions import NoSuchLawException
from lagasafn.pathing import make_xpath_from_node
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.utils import generate_legal_reference
from lagasafn.utils import search_xml_doc
from lagasafn.utils import traditionalize_law_nr
from lxml import etree
from lxml import html
from lxml.etree import _Element
from lxml.etree import _ElementTree
from math import floor
from os import listdir
from os.path import isfile
from pydantic import BaseModel
from pydantic import Field
from pydantic import computed_field
from typing import List

# FIXME: We do this to avoid feedback loops in importing, since advert-stuff required law-stuff and vice versa. The downside to this is that we lose type hinting. This should be solved using better module schemes instead.
AdvertManager = getattr(import_module("lagasafn.models.advert"), "AdvertManager")


class LawIndexInfo(BaseModel):
    codex_version: str = CURRENT_PARLIAMENT_VERSION
    date_from: datetime = datetime(1970, 1, 1, 0, 0, 0)
    date_to: datetime = datetime(1970, 1, 1, 0, 0, 0)
    total_count: int = 0
    empty_count: int = 0
    non_empty_count: int = 0


class LawEntry(BaseModel):
    """
    Intermediary model for a legal entry in the index.
    """
    codex_version: str = CURRENT_PARLIAMENT_VERSION
    identifier: str = ""
    _name: str = ""  # Retrieved using property `name`.
    nr: int = 0
    year: int = 0
    chapter_count: int = -1
    art_count: int = -1
    problems: dict = {}

    def __init__(
        self,
        identifier: str,
        name: str,
        codex_version: str = CURRENT_PARLIAMENT_VERSION,
        chapter_count: int = -1,
        art_count: int = -1,
        problems: dict = {}
    ):
        super().__init__()

        self.identifier = identifier
        self._name = name
        self.chapter_count = chapter_count
        self.art_count = art_count
        self.codex_version = codex_version

        try:
            self.nr, self.year = [int(v) for v in self.identifier.split("/")]
        except (ValueError, TypeError):
            raise LawException("Year must be an integer in '%s'" % self.identifier)

        self.problems = problems

    # Is function because it gets overridden by sub-class.
    @computed_field
    @property
    def name(self) -> str:
        return self._name

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

    def display_content_success(self):
        """
        Displays the content success as percentage.
        """

        if "content" not in self.problems:
            return "unknown"

        content_success = self.problems["content"]["success"]
        return "%.2f%%" % float(floor(content_success * 10000) / 100)

    def content_success(self):
        """
        Determines the status of the law, judging by known problem types.
        """

        return self.problems["content"]["success"]

    def __str__(self):
        return self.identifier


class LawIndex(BaseModel):
    info: LawIndexInfo = LawIndexInfo()
    laws: list[LawEntry] = []


class LawManager:
    @staticmethod
    @cache
    def index(codex_version: str) -> LawIndex:
        # Return variables.
        info = LawIndexInfo()
        laws = []

        info.codex_version = codex_version

        # Collect known problems to mix with the index.
        # A dictionary (map) will be generated with the law's identifier as a
        # key, which can then be quickly looked up when we iterate through the
        # index below.
        problem_map = {}
        problems = etree.parse(
            os.path.join(PROBLEMS_FILENAME % info.codex_version)
        ).getroot()
        for problem_law_entry in problems.findall("problem-law-entry"):
            statuses = {}
            for status_node in problem_law_entry.findall("status"):
                if "success" in status_node.attrib:
                    success = status_node.attrib["success"]
                else:
                    success = "0.0"
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
        xml_index = etree.parse(os.path.join(XML_INDEX_FILENAME % codex_version)).getroot()

        # Gather miscellaneous stuff into `info`.
        info.date_from = datetime.fromisoformat(xml_index.attrib["date-from"])
        info.date_to = datetime.fromisoformat(xml_index.attrib["date-to"])
        info.total_count = int(xml_index.xpath("/index/stats/total-count")[0].text)
        info.empty_count = int(xml_index.xpath("/index/stats/empty-count")[0].text)
        info.non_empty_count = int(xml_index.xpath("/index/stats/non-empty-count")[0].text)

        # Gather the laws in the index.
        for node_law_entry in xml_index.findall("law-entries/law-entry"):
            if node_law_entry.find("meta/is-empty").text == "true":
                continue

            problems = {}
            if node_law_entry.attrib["identifier"] in problem_map:
                problems = problem_map[node_law_entry.attrib["identifier"]]

            identifier = node_law_entry.attrib["identifier"]
            name = node_law_entry.find("name").text
            chapter_count = int(node_law_entry.find("meta/chapter-count").text)
            art_count = int(node_law_entry.find("meta/art-count").text)
            laws.append(LawEntry(
                identifier,
                name,
                info.codex_version,
                chapter_count,
                art_count,
                problems
            ))

        index = LawIndex()
        index.info = info
        index.laws = laws
        return index

    @staticmethod
    @cache
    def codex_versions() -> List[str]:
        codex_versions = []
        for item_name in listdir(XML_BASE_DIR):

            # Make sure that the directory name makes sense.
            if re.match(r"\d{3}[a-z]?", item_name) is None:
                continue

            # Make sure it has an index file.
            if not isfile(XML_INDEX_FILENAME % item_name):
                continue

            codex_versions.append(item_name)

        codex_versions.sort()

        return codex_versions

    @staticmethod
    def codex_version_at_date(timing: datetime) -> str:
        # This function is expensive but we are caching `LawManager.index` now,
        # so it should be fine. It makes no sense to `@cache` this one though,
        # because we won't be getting the same input consistently.
        result = ""
        codex_versions = LawManager.codex_versions()

        # The order here is important because we return the first codex version
        # we can find that meets the criteria.
        for codex_version in reversed(codex_versions):
            index = LawManager.index(codex_version)
            if timing >= index.info.date_to:
                result = codex_version
                break

        if len(result) == 0:
            raise LawException("Could not determine codex version at date: %s" % timing)

        return result

    @staticmethod
    def content_search(search_string: str, codex_version: str):

        results = []

        index = LawManager.index(codex_version)

        for law_entry in index.laws:
            law_xml = Law(law_entry.identifier, codex_version).xml()

            nodes = search_xml_doc(law_xml, search_string)

            findings = []
            for node in nodes:
                legal_reference = ""
                try:
                    legal_reference = generate_legal_reference(node.getparent(), skip_law=True)
                except:
                    pass
                findings.append({
                    "legal_reference": legal_reference,
                    "node": node,
                    "xpath": make_xpath_from_node(node),
                })

            if len(nodes):
                results.append({
                    "law_entry": law_entry,
                    "findings": findings,
                })

        return results


class Law(LawEntry):

    # Only used in `LawEntry`, at least for now.
    chapter_count: int = Field(default=-1, exclude=True)
    art_count: int = Field(default=-1, exclude=True)
    problems: dict = Field(default={}, exclude=True)

    def __init__(self, identifier: str, codex_version: str):

        # Name starts empty, so that the `name()` property below can lazy-fetch
        # it when it is needed.
        name = ""

        super().__init__(identifier, name, codex_version)

        # Private containers, essentially for caching.
        self._xml = None
        self._xml_references = None
        self._xml_text = ""
        self._html_text = ""
        self._superchapters = []
        self._chapters = []
        self._articles = []
        self._remote_contents = {}

        if not os.path.isfile(self.path()):
            raise NoSuchLawException("Could not find law '%s'" % self.identifier)

    @computed_field
    @property
    def name(self) -> str:
        if len(self._name):
            return self._name

        # Has its own cache mechanism, so this is fast.
        xml = self.xml()

        self._name = xml.find("name").text or ""

        return self._name

    @staticmethod
    def toc_name(text):
        """
        Makes the name fancy for displaying cleanly in the table-of-contents.
        """
        return strip_tags(text).replace("  ", " ").strip()

    @staticmethod
    def _make_art(art):
        """
        Centralized function for making an `art` in the specific context of
        this model, from XML data.
        """
        _art = {
            "nr": art.attrib["nr"],
            "nr_title": Law.toc_name(art.find("nr-title").text),
        }

        # Add name if it exists.
        art_name = art.find("name")
        if art_name is not None:
            _art["name"] = Law.toc_name(art_name.text)

        return _art

    def superchapters(self):
        if len(self._superchapters):
            return self._superchapters

        xml = self.xml()

        for superchapter in xml.findall("superchapter"):
            _superchapter = {
                "nr": superchapter.attrib["nr"],
                "chapters": [],
            }

            # Add nr-title if it exists.
            nr_title = superchapter.find("nr-title")
            if nr_title is not None:
                _superchapter["nr_title"] = nr_title.text

            # Add name if it exists.
            name = superchapter.find("name")
            if name is not None:
                _superchapter["name"] = name.text

            # Add chapters.
            for chapter in superchapter.findall("chapter"):
                _chapter = Law._make_chapter(chapter)
                _superchapter["chapters"].append(_chapter)

            self._superchapters.append(_superchapter)

        return self._superchapters

    @staticmethod
    def _make_chapter(chapter):
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

        return _chapter

    def chapters(self):
        if len(self._chapters):
            return self._chapters

        xml = self.xml()

        for chapter in xml.findall("chapter"):
            _chapter = self._make_chapter(chapter)
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
        return XML_FILENAME % (self.codex_version, self.year, self.nr)

    def xml(self):
        """
        Returns the law in XML object form.
        """
        if self._xml is None:
            self._xml = etree.parse(self.path())

        return self._xml

    def xml_text(self) -> str:
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

    def iter_structure(self):
        """
        Iterate such that we return the whole document, in order,
        but where each chunk is either a structural element, a chapter,
        an article or sub-article.

        The idea here is that we can create side-by-side comparisons and
        other such per-structural-unit displays.
        """
        xml = self.xml()

        chapters = xml.iter()
        for chapter in chapters:
            yield chapter

    def get_references(self):
        if self._xml_references is None:
            self._xml_references = etree.parse(XML_REFERENCES_FILENAME % CURRENT_PARLIAMENT_VERSION).getroot()

        nodes = self._xml_references.xpath(
            f"/references/law-ref-entry[@law-nr='{self.nr}' and @law-year='{self.year}']/node"
        )

        # We'll flatten out the references for simplicity. These will one day
        # belong to the nodes in the XML itself.
        references = []
        for node in nodes:
            for xml_ref in node.findall("reference"):
                references.append({
                    "location": node.attrib["location"],
                    "link_label": xml_ref.attrib["link-label"],
                    "inner_reference": xml_ref.attrib["inner-reference"],
                    "law_nr": xml_ref.attrib["law-nr"],
                    "law_year": xml_ref.attrib["law-year"],
                })

        return references

    def _get_doc_nr_and_parliament(self, href):
        pieces = href.split("/")
        parliament = int(pieces[4])
        doc_nr = int(pieces[6].rstrip(".html"))
        return doc_nr, parliament

    def _get_issue_status_from_doc(self, doc_nr, parliament):
        # Get issue.
        response = requests.get("https://www.althingi.is/altext/xml/thingskjol/thingskjal/?lthing=%d&skjalnr=%d" % (parliament, doc_nr))
        response.encoding = "utf-8"

        doc_xml = etree.fromstring(response.content)

        # Extract issue locating information.
        issue_node = doc_xml.xpath("/þingskjal/málalisti/mál")[0]
        issue_nr = int(issue_node.attrib["málsnúmer"])
        issue_parliament = int(issue_node.attrib["þingnúmer"])

        # Extract proposer information.
        proposer = None
        proposer_nodes = doc_xml.xpath("/þingskjal/þingskjal/flutningsmenn/flutningsmaður")
        if len(proposer_nodes) > 0:
            proposer_node = proposer_nodes[0]
            proposer_nr = int(proposer_node.attrib["id"])
            proposer = {
                "name": proposer_node.find("nafn").text,
                "link": "https://www.althingi.is/altext/cv/is/?nfaerslunr=%d" % proposer_nr,
            }

        # Get the issue data.
        response = requests.get("https://www.althingi.is/altext/xml/thingmalalisti/thingmal/?lthing=%d&malnr=%d" % (issue_parliament, issue_nr))
        response.encoding = "utf-8"

        issue_xml = etree.fromstring(response.content)
        status = issue_xml.xpath("/þingmál/mál/staðamáls")[0].text

        return status, proposer

    # FIXME: Find a better name for this thing. "Law box" makes no sense.
    # FIXME: This belongs in some sort of background processing instead of
    # being run every time a law is viewed.
    def _get_law_box(self, box_title):

        if "law_box" not in settings.FEATURES or not settings.FEATURES["law_box"]:
            return []

        box_links = []

        url = "https://www.althingi.is/lagas/nuna/%s%s.html" % (
            self.year,
            traditionalize_law_nr(self.nr)
        )

        if url in self._remote_contents:
            content = self._remote_contents[url]
        else:
            response = requests.get(url)

            if response.status_code != 200:
                return None

            # Parse the HTML content using lxml
            content = html.fromstring(response.content)

            self._remote_contents[url] = content

        h5_element = content.xpath("//h5[normalize-space(text())='%s']" % box_title)

        if h5_element is None or len(h5_element) == 0:
            return box_links

        ul_element = h5_element[0].getnext()
        if ul_element.tag != 'ul':
            return box_links

        for li_element in ul_element.xpath("li"):
            a_element = li_element.find("a")

            doc_nr, doc_parliament = self._get_doc_nr_and_parliament(a_element.attrib["href"])
            issue_status, proposer = self._get_issue_status_from_doc(doc_nr, doc_parliament)

            box_links.append({
                "link": a_element.attrib["href"],
                "law_name": a_element.attrib["title"],
                "document_name": a_element.text,
                "date": a_element.tail.lstrip(", "),
                "issue_status": issue_status,
                "proposer": proposer,
            })

        return box_links

    @cache
    def interim_adverts(self):
        return AdvertManager.by_affected_law(self.codex_version, self.nr, self.year)

    def get_ongoing_issues(self):
        return self._get_law_box("Frumvörp til breytinga á lögunum:")

    def editor_url(self):
        return settings.EDITOR_URL % (self.year, self.nr)

    def __str__(self):
        return self.identifier
