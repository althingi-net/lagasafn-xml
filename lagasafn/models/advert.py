from datetime import datetime
from dateutil.parser import isoparse
from lagasafn.constants import ADVERT_INDEX_FILENAME
from lagasafn.models import LawManager
from lxml import etree
from typing import List


class AdvertEntry:
    nr: int
    year: int
    published_date: datetime
    record_id: str
    description: str

    def identifier(self):
        return "%d/%d" % (self.nr, self.year)


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
    def index(codex_version: str) -> AdvertIndex:
        law_index = LawManager.index(codex_version)

        info = AdvertIndexInfo()
        info.codex_version = codex_version
        info.date_from = law_index.info.date_from
        info.date_to = law_index.info.date_to

        adverts = []
        advert_index_xml = etree.parse(ADVERT_INDEX_FILENAME).getroot()
        for entry_xml in advert_index_xml.findall("advert-entry"):
            published_date = isoparse(entry_xml.attrib["published-date"])

            if not (
                published_date >= info.date_from
                and published_date <= info.date_to
            ):
                continue

            entry = AdvertEntry()
            entry.nr = int(entry_xml.attrib["nr"])
            entry.year = int(entry_xml.attrib["nr"])
            entry.published_date = published_date
            entry.record_id = entry_xml.attrib["record-id"]
            entry.description = entry_xml.attrib["description"]
            adverts.append(entry)

        index = AdvertIndex()
        index.info = info
        index.adverts = adverts

        return index
