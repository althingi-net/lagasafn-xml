from datetime import datetime
from dateutil.parser import isoparse
from functools import cache
from importlib import import_module
from lagasafn.constants import ADVERT_FILENAME
from lagasafn.constants import ADVERT_INDEX_FILENAME
from lagasafn.exceptions import AdvertException
from lxml import etree
from lxml.etree import _Element
from os.path import isfile
from typing import List


class AdvertArticle:
    nr: str = ""
    original: str = ""


class AdvertEntry:
    identifier: str = ""
    nr: int
    year: int
    published_date: datetime
    record_id: str = ""
    description: str = ""
    article_count: int = 0

    # We store these as identifiers ("45/2024") instead of separate `nr` and
    # `year` because these are used for lookup, and we'd rather look up by the
    # whole value rather than look up by two values.
    affected_law_identifiers: List[str] = []

    def __init__(self, identifier: str):
        nr, year = identifier.split("/")
        self.nr = int(nr)
        self.year = int(year)

        self.identifier = identifier
        self.affected_law_identifiers = []

    def original_url(self):
        return "https://www.stjornartidindi.is/Advert.aspx?RecordID=%s" % self.record_id


class Advert(AdvertEntry):

    _xml: _Element | None = None
    _articles: List[AdvertArticle] | None = None

    def __init__(self, identifier: str):
        super().__init__(identifier)

        if not isfile(self.path()):
            raise AdvertException("Could not find XML file for advert '%s'" % self.identifier)

        # Will load the data from XML to object.
        self.xml()

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


class AdvertIndexInfo:
    codex_version: str
    date_from: datetime
    date_to: datetime
    total_count: int


class AdvertIndex:
    info: AdvertIndexInfo = AdvertIndexInfo()
    adverts: List[AdvertEntry] = []


class AdvertManager:
    @staticmethod
    @cache
    def index(codex_version: str) -> AdvertIndex:
        LawManager = getattr(import_module("lagasafn.models"), "LawManager")
        law_index = LawManager.index(codex_version)

        info = AdvertIndexInfo()
        info.codex_version = codex_version
        info.date_from = law_index.info.date_from
        info.date_to = law_index.info.date_to

        adverts = []
        advert_index_xml = etree.parse(ADVERT_INDEX_FILENAME).getroot()
        for entry_xml in advert_index_xml.xpath("advert-entry[@applied-to-codex-version='%s']" % codex_version):

            identifier = "%s/%s" % (entry_xml.attrib["nr"], entry_xml.attrib["year"])

            entry = AdvertEntry(identifier)
            entry.published_date = isoparse(entry_xml.attrib["published-date"])
            entry.record_id = entry_xml.attrib["record-id"]
            entry.description = entry_xml.attrib["description"]
            entry.article_count = int(entry_xml.attrib["article-count"])
            for affected_law in entry_xml.xpath("affected-laws/affected-law"):
                entry.affected_law_identifiers.append(affected_law.text)
            adverts.append(entry)

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
