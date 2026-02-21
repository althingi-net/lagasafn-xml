from datetime import datetime
from dateutil.parser import isoparse
from functools import cache
from importlib import import_module
from lagasafn.constants import (
    ADVERT_FILENAME,
    ADVERT_ORIGINAL_FILENAME,
    ADVERT_REMOTE_FILENAME,
)
from lagasafn.constants import ADVERT_INDEX_FILENAME
from lagasafn.exceptions import AdvertException
from lagasafn.utils import get_all_text, xml_text_to_html_text
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


class AdvertIntentElement(BaseModel):
    xml: str
    text: str


class AdvertIntent(BaseModel):
    nr: int
    action: str
    action_xpath: str
    original: Optional[AdvertIntentElement] = None
    applied: Optional[AdvertIntentElement] = None
    next: Optional[AdvertIntentElement] = None


class AdvertIntentLaw(BaseModel):
    identifier: str
    intents: List[AdvertIntent]


class AdvertIntentDetails(BaseModel):
    codex_version: str
    next_codex_version: Optional[str] = None
    enact_date: str
    laws: List[AdvertIntentLaw]


class Advert(AdvertEntry):

    _xml: _Element | None = None
    _articles: List[AdvertArticle] | None = None
    _xml_text: str = ""
    _original_xml_text: str = ""

    # Original XML content of the full advert, converted to HTML text
    original_html_text: str = Field(default="", required=True)

    # Intent XML containing all <intents> elements extracted from the advert, converted to HTML text
    intent_html_text: str = Field(default="", required=True)

    def __init__(self, identifier: str):
        super().__init__(identifier)

        if not isfile(self.path()):
            raise AdvertException(
                "Could not find XML file for advert '%s'" % self.identifier
            )

        # Will load the data from XML to object.
        self.xml()

        # Set original HTML text and intent HTML text
        self.original_html_text = self.get_original_html_text()
        self.intent_html_text = self.get_intent_html_text()

    def path(self):
        return ADVERT_FILENAME % (self.year, self.nr)

    def remote_path(self):
        return ADVERT_REMOTE_FILENAME % (self.year, self.nr)

    def original_path(self):
        return ADVERT_ORIGINAL_FILENAME % (self.year, self.nr)

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

    def original_xml_text(self) -> str:
        """
        Returns the original advert in XML text form.
        """

        # Just return the content if we already have it.
        if len(self._original_xml_text) > 0:
            return self._original_xml_text

        # Try original_path first, fall back to remote_path if it doesn't exist
        if isfile(self.original_path()):
            with open(self.original_path()) as f:
                self._original_xml_text = f.read()
        else:
            with open(self.remote_path()) as f:
                self._original_xml_text = f.read()

        return self._original_xml_text

    def get_original_html_text(self):
        """
        Generates the advert in HTML text form.
        """

        # Just return the content if we already have it.
        if len(self.original_html_text) > 0:
            return self.original_html_text

        # Make sure we have the XML.
        xml_text = self.original_xml_text()

        # Convert XML to HTML using shared utility function.
        return xml_text_to_html_text(xml_text)

    def get_intent_html_text(self):
        """
        Generates the advert in HTML text form.
        """

        # Just return the content if we already have it.
        if len(self.intent_html_text) > 0:
            return self.intent_html_text

        # Make sure we have the XML.
        xml_text = self.xml_text()

        # Convert XML to HTML using shared utility function.
        return xml_text_to_html_text(xml_text)

    def get_intent_details(self) -> Optional[AdvertIntentDetails]:
        """
        Returns intent details with element comparisons for each affected law.
        Returns an AdvertIntentDetails model with intent information.
        """

        Law = getattr(import_module("lagasafn.models.law"), "Law")
        LawManager = getattr(import_module("lagasafn.models.law"), "LawManager")

        advert_xml = self.xml()
        codex_version = advert_xml.get("applied-to-codex-version")
        if not codex_version:
            return None

        # Get enact date
        enact_date = None
        for intent in advert_xml.findall(".//intent"):
            if intent.get("action") == "enact":
                enact_date = intent.get("timing")
                break

        if not enact_date:
            return None

        next_codex_version = LawManager.get_next_codex_version(codex_version)

        # Group intents by law
        law_intents = {}
        for intent in advert_xml.findall(".//intent"):
            action = intent.get("action")
            if action == "enact":
                continue
            elif action == "repeal":
                law_id = intent.get("action-identifier")
                if law_id:
                    if law_id not in law_intents:
                        law_intents[law_id] = []
                    law_intents[law_id].append(intent)
            else:
                law_nr = intent.get("action-law-nr")
                law_year = intent.get("action-law-year")
                if law_nr and law_year:
                    law_id = f"{law_nr}/{law_year}"
                    if law_id not in law_intents:
                        law_intents[law_id] = []
                    law_intents[law_id].append(intent)

        laws = []

        for law_id, intents in law_intents.items():
            intent_list = []

            # Load original law (before advert was applied) from codex_version
            original_law = Law(law_id, codex_version)
            original_xml = original_law.xml().getroot()

            # Load applied law (after advert was applied) from codex_version
            applied_law = Law(law_id, codex_version, applied_timing=enact_date)
            applied_xml = applied_law.xml().getroot()

            # Load next law if next codex version exists
            next_xml = None
            if next_codex_version:
                next_law = Law(law_id, next_codex_version)
                next_xml = next_law.xml().getroot()

            for intent_nr, intent in enumerate(intents, start=1):
                action_xpath = intent.get("action-xpath", "")
                original_element = None
                applied_element = None
                next_element = None

                if action_xpath:
                    # Get original element (before advert was applied)
                    original_elements = original_xml.xpath(action_xpath)
                    if original_elements:
                        original_element = AdvertIntentElement(
                            xml=etree.tostring(
                                original_elements[0],
                                pretty_print=True,
                                encoding="unicode",
                            ),
                            text=get_all_text(original_elements[0]),
                        )

                    # Get applied element (after advert was applied)
                    applied_elements = applied_xml.xpath(action_xpath)
                    if applied_elements:
                        applied_element = AdvertIntentElement(
                            xml=etree.tostring(
                                applied_elements[0],
                                pretty_print=True,
                                encoding="unicode",
                            ),
                            text=get_all_text(applied_elements[0]),
                        )

                    # Get next element (from next codex version, if available)
                    if next_xml:
                        next_elements = next_xml.xpath(action_xpath)
                        if next_elements:
                            next_element = AdvertIntentElement(
                                xml=etree.tostring(
                                    next_elements[0],
                                    pretty_print=True,
                                    encoding="unicode",
                                ),
                                text=get_all_text(next_elements[0]),
                            )

                intent_list.append(
                    AdvertIntent(
                        nr=intent_nr,
                        action=intent.get("action", ""),
                        action_xpath=action_xpath,
                        original=original_element,
                        applied=applied_element,
                        next=next_element,
                    )
                )

            laws.append(AdvertIntentLaw(identifier=law_id, intents=intent_list))

        return AdvertIntentDetails(
            codex_version=codex_version,
            next_codex_version=next_codex_version,
            enact_date=enact_date,
            laws=laws,
        )


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
    def by_affected_law(codex_version: str, nr: str, year: int) -> List[AdvertEntry]:
        identifier = "%s/%s" % (nr, year)
        index = AdvertManager.index(codex_version)

        adverts = []
        for advert in index.adverts:
            if identifier in advert.affected_law_identifiers:
                adverts.append(advert)

        return adverts
