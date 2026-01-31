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
from lagasafn.constants import ADVERT_INDEX_FILENAME
from lagasafn.exceptions import LawException
from lagasafn.exceptions import NoSuchLawException
from lagasafn.pathing import make_xpath_from_node
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.utils import generate_legal_reference
from lagasafn.utils import search_xml_doc
from lagasafn.utils import traditionalize_law_nr
from lagasafn.utils import xml_text_to_html_text
from lxml import etree
from lxml import html
from lxml.etree import _Element
from math import floor
from os import listdir
from os.path import isfile
from pydantic import BaseModel
from pydantic import Field
from typing import List

# FIXME: We do this to avoid feedback loops in importing, since advert-stuff required law-stuff and vice versa. The downside to this is that we lose type hinting. This should be solved using better module schemes instead.
_advert_module = import_module("lagasafn.models.advert")
AdvertManager = getattr(_advert_module, "AdvertManager")
Advert = getattr(_advert_module, "Advert")


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

    identifier: str
    name: str
    codex_version: str
    chapter_count: int
    art_count: int
    problems: dict
    versions: list[str]
    nr: int
    year: int

    def __init__(
        self,
        identifier: str,
        name: str,
        codex_version: str = CURRENT_PARLIAMENT_VERSION,
        chapter_count: int = -1,
        art_count: int = -1,
        problems: dict = {},
        versions: list[str] = [],
    ):
        try:
            nr, year = [int(v) for v in identifier.split("/")]
        except (ValueError, TypeError):
            raise LawException("Year must be an integer in '%s'" % identifier)

        super().__init__(
            identifier=identifier,
            name=name,
            codex_version=codex_version,
            chapter_count=chapter_count,
            art_count=art_count,
            problems=problems,
            versions=versions,
            nr=nr,
            year=year,
        )

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
        xml_index = etree.parse(
            os.path.join(XML_INDEX_FILENAME % codex_version)
        ).getroot()

        # Gather miscellaneous stuff into `info`.
        info.date_from = datetime.fromisoformat(xml_index.attrib["date-from"])
        info.date_to = datetime.fromisoformat(xml_index.attrib["date-to"])
        info.total_count = int(xml_index.xpath("/index/stats/total-count")[0].text)
        info.empty_count = int(xml_index.xpath("/index/stats/empty-count")[0].text)
        info.non_empty_count = int(
            xml_index.xpath("/index/stats/non-empty-count")[0].text
        )

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
            versions = LawManager.versions_for_codex(identifier, info.codex_version)
            try:
                entry = LawEntry(
                    identifier,
                    name,
                    info.codex_version,
                    chapter_count,
                    art_count,
                    problems,
                    versions,
                )
                laws.append(entry)
            except Exception:
                # Skip failing entries
                pass

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
    @cache
    def versions_for_codex(identifier: str, codex_version: str) -> list[str]:
        """
        Returns all known version identifiers for a law within a given codex version.
        Uses the applied directory to find applied versions.
        """

        versions: set[str] = set()
        versions.add(codex_version)

        # Parse the law identifier (format: "nr/year", e.g., "88/2011")
        try:
            nr_str, year_str = identifier.split("/")
            law_nr = int(nr_str)
            law_year = int(year_str)
        except (ValueError, AttributeError):
            # If we can't parse the identifier, return just the base codex version.
            return [codex_version]

        # Look in the applied directory for this codex version
        applied_dir = os.path.join(XML_BASE_DIR, codex_version, "applied")
        if not os.path.exists(applied_dir) or not os.path.isdir(applied_dir):
            # If the applied directory doesn't exist, return just the base codex version.
            return [codex_version]

        # Find all applied files for this law
        # File format: {year}.{nr}-{enact_date}.xml
        pattern = f"{law_year}.{law_nr}-"
        try:
            for filename in listdir(applied_dir):
                if not filename.endswith(".xml"):
                    continue
                if not filename.startswith(pattern):
                    continue

                # Extract the enact date from the filename
                # Format: {year}.{nr}-{enact_date}.xml
                # Remove .xml extension and split by '-'
                base_name = filename[:-4]  # Remove .xml
                parts = base_name.split("-", 1)
                if len(parts) == 2:
                    enact_date = parts[1]
                    versions.add(f"{codex_version}-{enact_date}")
        except Exception:
            pass

        other_versions = sorted(v for v in versions if v != codex_version)
        return [codex_version, *other_versions]

    @staticmethod
    @cache
    def all_versions(identifier: str) -> list[str]:
        """
        Returns all known versions for a law across all codex versions.
        Returns a flat list of all version strings (both codex versions and applied versions).
        """
        all_versions_list: list[str] = []

        # Parse identifier to get law number and year
        try:
            nr, year = identifier.split("/")
            year = int(year)
        except (ValueError, TypeError):
            # Invalid identifier format
            return all_versions_list

        for codex_version in LawManager.codex_versions():
            # Check if law file exists in this codex version
            law_path = XML_FILENAME % (codex_version, year, nr)
            if not os.path.isfile(law_path):
                continue

            try:
                # Get all versions (codex + applied) for this law in this codex version
                versions = LawManager.versions_for_codex(identifier, codex_version)
                all_versions_list.extend(versions)
            except Exception:
                # If we can't get versions for any reason, skip this codex version
                continue

        # Remove duplicates and sort for stable ordering
        return sorted(set(all_versions_list))

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
    def get_next_codex_version(codex_version: str) -> str | None:
        """
        Get the next codex version after the given one.

        Args:
            codex_version: The codex version to get the next version for

        Returns:
            The next codex version, or None if there is no next version
        """
        codex_versions = LawManager.codex_versions()
        try:
            current_index = codex_versions.index(codex_version)
            if current_index < len(codex_versions) - 1:
                return codex_versions[current_index + 1]
        except ValueError:
            # codex_version not in list
            pass
        return None

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
                    legal_reference = generate_legal_reference(
                        node.getparent(), skip_law=True
                    )
                except:
                    pass
                findings.append(
                    {
                        "legal_reference": legal_reference,
                        "node": node,
                        "xpath": make_xpath_from_node(node),
                    }
                )

            if len(nodes):
                results.append(
                    {
                        "law_entry": law_entry,
                        "findings": findings,
                    }
                )

        return results


class Article(BaseModel):
    nr: str
    nr_title: str
    name: str

    def __init__(self, nr: str, nr_title: str, name: str = ""):
        super().__init__(nr=nr, nr_title=nr_title, name=name)


class Chapter(BaseModel):
    nr: str
    nr_title: str
    name: str
    articles: list[Article]

    def __init__(
        self, nr: str, nr_title: str = "", name: str = "", articles: list[Article] = []
    ):
        super().__init__(nr=nr, nr_title=nr_title, name=name, articles=articles)


class Law(LawEntry):

    # Only used in `LawEntry`, at least for now, so excluded here.
    chapter_count: int = Field(exclude=True)
    art_count: int = Field(exclude=True)
    problems: dict = Field(exclude=True)
    applied_timing: str | None = Field(default=None, exclude=True)
    chapters: list[Chapter] = Field(default_factory=list, required=True)

    # HTML that should be displayable in a browser, assuming CSS for styling
    # and hiding elements that are irrelevant to a human reader.
    versions: list[str] = Field(default_factory=list)
    html_text: str = Field(default="", required=True)

    def __init__(
        self, identifier: str, codex_version: str, applied_timing: str | None = None
    ):

        # NOTE: The `name` is temporarily set first here, because in order to
        # load the XML, the parent class needs the `identifier`, but the `Law`
        # class determines the name from the XML while the parent class
        # receives it during creation. The name gets updated immediately after
        # the parent class's constructor has been called.
        super().__init__(identifier, "[not-ready]", codex_version)

        self.applied_timing = applied_timing
        # Private containers, essentially for caching.
        self._xml = None
        self._xml_references = None
        self._xml_text = ""
        self._superchapters = []
        self._articles = []
        self._remote_contents = {}

        # NOTE: This used to be lazy-fetched. If this turns out to be too slow
        # because we're constantly creating these objects without needing to
        # load their content, we should create another constructor, or a
        # chaining `load()` function or something of the sort.
        self.name = self.xml().find("name").text or ""
        self.html_text = self.get_html_text()
        self.chapters = self.get_chapters()
        self.versions = LawManager.all_versions(self.identifier)

        if not os.path.isfile(self.path()):
            raise NoSuchLawException("Could not find law '%s'" % self.identifier)

    # FIXME: It's unclear why this function exists. If there's a reason for it,
    # that reason should be given. If there's no reason, it should be removed
    # in favor of better data. It makes names fancy for a table of contents,
    # but doesn't explain why they're not already fancy enough.
    @staticmethod
    def toc_name(text):
        """
        Makes the name fancy for displaying cleanly in the table-of-contents.
        """
        return strip_tags(text).replace("  ", " ").strip()

    @staticmethod
    def _make_art(xml_art):
        """
        Centralized function for making an `art` in the specific context of
        this model, from XML data.
        """
        art = Article(
            nr=xml_art.attrib["nr"],
            nr_title=Law.toc_name(xml_art.find("nr-title").text),
        )

        # Add name if it exists.
        art_name = xml_art.find("name")
        if art_name is not None:
            art.name = Law.toc_name(art_name.text)

        return art

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
    def _make_chapter(xml_chapter: _Element) -> Chapter:
        chapter = Chapter(nr=xml_chapter.attrib["nr"])

        # Add nr-title if it exists.
        xml_nr_title = xml_chapter.find("nr-title")
        if xml_nr_title is not None:
            chapter.nr_title = xml_nr_title.text or ""

        # Add name if it exists.
        xml_name = xml_chapter.find("name")
        if xml_name is not None:
            chapter.name = xml_name.text

        # Add articles.name
        for xml_art in xml_chapter.findall("art"):
            art = Law._make_art(xml_art)
            chapter.articles.append(art)

        return chapter

    def get_chapters(self) -> list[Chapter]:
        if len(self.chapters):
            return self.chapters

        return [Law._make_chapter(c) for c in self.xml().findall("chapter")]

    def articles(self):
        if len(self._articles):
            return self._articles

        xml = self.xml()

        for art in xml.findall("art"):
            _art = Law._make_art(art)
            self._articles.append(_art)

        return self._articles

    def path(self):
        """
        Returns the filesystem path to this law's XML representation.
        """

        if self.applied_timing:
            applied_dir = os.path.join(XML_BASE_DIR, self.codex_version, "applied")

            applied_filename = "%d.%d-%s.xml" % (
                self.year,
                self.nr,
                self.applied_timing,
            )
            return os.path.join(applied_dir, applied_filename)

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

    def get_html_text(self):
        """
        Generates the law in HTML text form.
        """

        # Just return the content if we already have it.
        if len(self.html_text) > 0:
            return self.html_text

        # Make sure we have the XML.
        xml_text = self.xml_text()

        return xml_text_to_html_text(xml_text)

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
            self._xml_references = etree.parse(
                XML_REFERENCES_FILENAME % CURRENT_PARLIAMENT_VERSION
            ).getroot()

        nodes = self._xml_references.xpath(
            f"/references/law-ref-entry[@law-nr='{self.nr}' and @law-year='{self.year}']/node"
        )

        # We'll flatten out the references for simplicity. These will one day
        # belong to the nodes in the XML itself.
        references = []
        for node in nodes:
            for xml_ref in node.findall("reference"):
                references.append(
                    {
                        "location": node.attrib["location"],
                        "link_label": xml_ref.attrib["link-label"],
                        "inner_reference": xml_ref.attrib["inner-reference"],
                        "law_nr": xml_ref.attrib["law-nr"],
                        "law_year": xml_ref.attrib["law-year"],
                    }
                )

        return references

    def _get_doc_nr_and_parliament(self, href):
        pieces = href.split("/")
        parliament = int(pieces[4])
        doc_nr = int(pieces[6].rstrip(".html"))
        return doc_nr, parliament

    def _get_issue_status_from_doc(self, doc_nr, parliament):
        # Get issue.
        response = requests.get(
            "https://www.althingi.is/altext/xml/thingskjol/thingskjal/?lthing=%d&skjalnr=%d"
            % (parliament, doc_nr)
        )
        response.encoding = "utf-8"

        doc_xml = etree.fromstring(response.content)

        # Extract issue locating information.
        issue_node = doc_xml.xpath("/þingskjal/málalisti/mál")[0]
        issue_nr = int(issue_node.attrib["málsnúmer"])
        issue_parliament = int(issue_node.attrib["þingnúmer"])

        # Extract proposer information.
        proposer = None
        proposer_nodes = doc_xml.xpath(
            "/þingskjal/þingskjal/flutningsmenn/flutningsmaður"
        )
        if len(proposer_nodes) > 0:
            proposer_node = proposer_nodes[0]
            proposer_nr = int(proposer_node.attrib["id"])
            proposer = {
                "name": proposer_node.find("nafn").text,
                "link": "https://www.althingi.is/altext/cv/is/?nfaerslunr=%d"
                % proposer_nr,
            }

        # Get the issue data.
        response = requests.get(
            "https://www.althingi.is/altext/xml/thingmalalisti/thingmal/?lthing=%d&malnr=%d"
            % (issue_parliament, issue_nr)
        )
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
            traditionalize_law_nr(self.nr),
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
        if ul_element.tag != "ul":
            return box_links

        for li_element in ul_element.xpath("li"):
            a_element = li_element.find("a")

            doc_nr, doc_parliament = self._get_doc_nr_and_parliament(
                a_element.attrib["href"]
            )
            issue_status, proposer = self._get_issue_status_from_doc(
                doc_nr, doc_parliament
            )

            box_links.append(
                {
                    "link": a_element.attrib["href"],
                    "law_name": a_element.attrib["title"],
                    "document_name": a_element.text,
                    "date": a_element.tail.lstrip(", "),
                    "issue_status": issue_status,
                    "proposer": proposer,
                }
            )

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
