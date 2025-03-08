from lagasafn.constants import ADVERT_DIR
from lagasafn.constants import ADVERT_INDEX_FILENAME
from lagasafn.constants import ADVERT_REMOTES_DIR
from lagasafn.constants import ADVERT_REMOTE_FILENAME
from lagasafn.advert.parsers import parse_advert
from lagasafn.exceptions import AdvertException
from lagasafn.utils import write_xml
from lxml import etree
from lxml.etree import _Element
from lxml.builder import E
from os import listdir
from os import path
from typing import List
import re


def convert_adverts(advert_identifiers: List[str] = []):
    """
    Converts all remote adverts into proper XML.
    """

    filenames = []
    if len(advert_identifiers) > 0:
        for identifier in advert_identifiers:
            try:
                nr, year = identifier.split("/")
                nr = int(nr)
                year = int(year)
            except ValueError:
              raise AdvertException("Invalid advert identifier: %s" % identifier)

            expected_filename = ADVERT_REMOTE_FILENAME % (year, nr)

            if not path.isfile(expected_filename):
                raise AdvertException("Advert %d/%d not found." % (nr, year))

            filenames.append(path.basename(expected_filename))
    else:
        # Get all available filenames if nothing is specified.
        filenames = [
            f
            for f in listdir(ADVERT_REMOTES_DIR)
            if re.match(r"^\d{4}\.\d{1,3}\.remote\.xml$", f)
        ]

    # An ordered list of "year"/"nr" combinations to process.
    convertibles = []

    # Turn filenames into convertibles.
    for filename in filenames:
        parts = filename.split(".")
        convertibles.append(
            {
                "year": int(parts[0]),
                "nr": int(parts[1]),
            }
        )

    convertibles = sorted(convertibles, key=lambda c: (c["year"], c["nr"]))

    for convertible in convertibles:
        convert_advert(convertible["year"], convertible["nr"])


def convert_advert(year, nr):
    """
    Converts a single remote advert XML to a proper advert XML.
    """

    print("Converting %d/%d..." % (nr, year), end="", flush=True)

    xml_remote = etree.parse(
        path.join(ADVERT_REMOTES_DIR, "%d.%d.remote.xml" % (year, nr))
    ).getroot()

    advert_type = xml_remote.xpath("//tr[@class='advertType']/td/br")[0].tail.lower()

    if advert_type == "lög":
        xml_advert = parse_advert(xml_remote)
    else:
        print(" skipping (unsupported type '%s')" % advert_type)
        return

    write_xml(xml_advert, path.join(ADVERT_DIR, "%d.%d.advert.xml" % (year, nr)))

    print(" done")


def create_index():
    """
    Creates an index of adverts that exist in XML form.
    """

    print("Creating index...", end="", flush=True)

    advert_index: _Element = E("advert-index")

    for advert_filename in listdir(ADVERT_DIR):
        fullpath = path.join(ADVERT_DIR, advert_filename)
        advert = etree.parse(fullpath).getroot()

        advert_entry = E("advert-entry", {
            "type": advert.attrib["type"],
            "year": advert.attrib["year"],
            "nr": advert.attrib["nr"],
            "published-date": advert.attrib["published-date"],
            "record-id": advert.attrib["record-id"],
            "description": advert.find("description").text,
            "article-count": str(len(advert.xpath("//art"))),
        })

        advert_index.append(advert_entry)

        print(".", end="", flush=True)

    # Sort index for consistency's sake.
    advert_index[:] = sorted(
        advert_index,
        key=lambda n: (int(n.attrib["year"]), int(n.attrib["nr"])),
        reverse=True
    )

    write_xml(advert_index, ADVERT_INDEX_FILENAME)

    print(" done")
