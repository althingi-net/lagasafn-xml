from datetime import datetime
from dateutil.parser import isoparse
from functools import cache
from importlib import import_module
from lagasafn.constants import ADVERT_FILENAME
from lagasafn.constants import ADVERT_INDEX_FILENAME
from lagasafn.exceptions import AdvertException
from lagasafn.utils import xml_text_to_html_text
from lxml import etree
from lxml.etree import _Element
from os.path import isfile
from pydantic import BaseModel
from pydantic import Field
from typing import List
from typing import Optional

from lagasafn.settings import CURRENT_PARLIAMENT_VERSION


class AdvertArticle:
    nr: str = ""
    original: str = ""


class AdvertEntry(BaseModel):
    identifier: str = ""
    nr: int
    year: int
    published_date: Optional[datetime] = None
    record_id: str = ""
    description: str = ""
    article_count: int = 0

    # We store these as identifiers ("45/2024") instead of separate `nr` and
    # `year` because these are used for lookup, and we'd rather look up by the
    # whole value rather than look up by two values.
    affected_law_identifiers: List[str]

    def __init__(
        self,
        identifier: str = "",
        nr: int = 0,
        year: int = 0,
        published_date: Optional[datetime] = None,
        record_id: str = "",
        description: str = "",
        article_count: int = 0,
        affected_law_identifiers: List[str] = None,
    ):
        # If only identifier is provided, parse it to get nr and year
        if identifier and not nr and not year:
            nr_str, year_str = identifier.split("/")
            nr = int(nr_str)
            year = int(year_str)

        if affected_law_identifiers is None:
            affected_law_identifiers = []

        super().__init__(
            identifier=identifier,
            nr=nr,
            year=year,
            published_date=published_date,
            record_id=record_id,
            description=description,
            article_count=article_count,
            affected_law_identifiers=affected_law_identifiers,
        )

    def original_url(self):
        return "https://www.stjornartidindi.is/Advert.aspx?RecordID=%s" % self.record_id


class Advert(AdvertEntry):

    _xml: _Element | None = None
    _articles: List[AdvertArticle] | None = None
    _xml_text: str = ""

    # HTML that should be displayable in a browser, assuming CSS for styling
    # and hiding elements that are irrelevant to a human reader.
    html_text: str = Field(default="", required=True)

    def __init__(self, identifier: str):
        super().__init__(identifier)

        if not isfile(self.path()):
            raise AdvertException(
                "Could not find XML file for advert '%s'" % self.identifier
            )

        # Will load the data from XML to object.
        self.xml()

        # Generate HTML text after loading XML
        self.html_text = self.get_html_text()

    def path(self):
        return ADVERT_FILENAME % (self.year, self.nr)

    def xml(self):
        """
        Returns the advert in XML object form.
        """
        if self._xml is None:
            self._xml = etree.parse(self.path()).getroot()

            # NOTE: `self.nr` and `self.year` already set by superclass.
            self.published_date = isoparse(self._xml.attrib["published-date"])
            self.record_id = self._xml.attrib["record-id"]
            self.description = self._xml.find("description").text.__str__()

            self.affected_law_identifiers = [
                affected_law.text
                for affected_law in self._xml.xpath("affected-laws/affected-law")
            ]

        return self._xml

    @staticmethod
    def _make_art(art: _Element) -> AdvertArticle:
        _art = AdvertArticle()
        _art.nr = art.attrib["nr"]
        _art.original = etree.tostring(art.find("original"), encoding="unicode")

        return _art

    def articles(self) -> List[AdvertArticle]:
        if self._articles is not None:
            return self._articles

        xml = self.xml()

        self._articles = []
        for art in xml.xpath("//advert-art"):
            _art = Advert._make_art(art)
            self._articles.append(_art)

        return self._articles

    def xml_text(self) -> str:
        """
        Returns the advert in XML text form.
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
        Generates the advert in HTML text form.
        """

        # Just return the content if we already have it.
        if len(self.html_text) > 0:
            return self.html_text

        # Make sure we have the XML.
        xml_text = self.xml_text()

        # Convert XML to HTML using shared utility function.
        return xml_text_to_html_text(xml_text)


class AdvertIndexInfo(BaseModel):
    codex_version: str = CURRENT_PARLIAMENT_VERSION
    date_from: datetime = datetime(1970, 1, 1, 0, 0, 0)
    date_to: datetime = datetime(1970, 1, 1, 0, 0, 0)
    total_count: int = 0


class AdvertIndex(BaseModel):
    info: AdvertIndexInfo = AdvertIndexInfo()
    adverts: List[AdvertEntry] = []


class AdvertManager:
    @staticmethod
    @cache
    def index(codex_version: str) -> AdvertIndex:
        LawManager = getattr(import_module("lagasafn.models.law"), "LawManager")
        law_index = LawManager.index(codex_version)

        info = AdvertIndexInfo()
        info.codex_version = codex_version
        info.date_from = law_index.info.date_from
        info.date_to = law_index.info.date_to

        adverts = []
        advert_index_xml = etree.parse(ADVERT_INDEX_FILENAME).getroot()
        for entry_xml in advert_index_xml.xpath(
            "advert-entry[@applied-to-codex-version='%s']" % codex_version
        ):

            identifier = "%s/%s" % (entry_xml.attrib["nr"], entry_xml.attrib["year"])
            affected_law_identifiers = [
                affected_law.text
                for affected_law in entry_xml.xpath("affected-laws/affected-law")
            ]
            entry = AdvertEntry(
                identifier=identifier,
                published_date=isoparse(entry_xml.attrib["published-date"]),
                record_id=entry_xml.attrib["record-id"],
                description=entry_xml.attrib["description"],
                article_count=int(entry_xml.attrib["article-count"]),
                affected_law_identifiers=affected_law_identifiers,
            )
            adverts.append(entry)

        info.total_count = len(adverts)

        index = AdvertIndex()
        index.info = info
        index.adverts = adverts

        return index

    @staticmethod
    @cache
    def by_affected_law(codex_version: str, nr: str, year: int) -> List[Advert]:
        identifier = "%s/%s" % (nr, year)
        index = AdvertManager.index(codex_version)

        adverts = []
        for advert in index.adverts:
            if identifier in advert.affected_law_identifiers:
                adverts.append(advert)

        return adverts
