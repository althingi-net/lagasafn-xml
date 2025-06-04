from lagasafn.constants import ADVERT_DIR
from lagasafn.constants import ADVERT_INDEX_FILENAME
from lagasafn.advert.filesystem import get_original_advert_identifiers
from lagasafn.advert.filesystem import get_original_advert_xml
from lagasafn.advert.parsers import parse_advert
from lagasafn.exceptions import AdvertException
from lagasafn.exceptions import IntentParsingException
from lagasafn.exceptions import ReferenceParsingException
from lagasafn.utils import write_xml
from lxml import etree
from lxml.etree import _Element
from lxml.builder import E
from os import listdir
from os import path


def convert_adverts(requested_identifiers: list[str] = []):
    """
    Converts all remote adverts into proper XML.
    """

    # Identifiers that will end up being converted.
    identifiers = []

    # Identifiers for which there is original data.
    original_identifiers = get_original_advert_identifiers()

    if len(requested_identifiers) > 0:
        # Check if all the requested adverts exist.
        for requested_identifier in requested_identifiers:
            if not requested_identifier in original_identifiers:
                raise AdvertException("Advert %s not found." % requested_identifier)

        identifiers = requested_identifiers
    else:
        identifiers = original_identifiers

    # An ordered list of "year"/"nr" combinations to process.
    # We are basically doing this to sort this easily.
    convertibles = []
    for identifier in identifiers:
        nr, year = [int(part) for part in identifier.split("/")]
        convertibles.append(
            {
                "year": year,
                "nr": nr,
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

    xml_remote = get_original_advert_xml(year, nr)

    advert_type = xml_remote.xpath("//tr[@class='advertType']/td/br")[0].tail.lower()

    if advert_type != "lög":
        print(" skipping (unsupported type '%s')" % advert_type)
        return

    try:
        xml_advert = parse_advert(xml_remote)
        write_xml(xml_advert, path.join(ADVERT_DIR, "%d.%d.advert.xml" % (year, nr)))
        print(" done")
    except (IntentParsingException, ReferenceParsingException) as ex:
        print(" failed with %s exception:" % type(ex).__name__)
        print(ex)
        print()

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
            "applied-to-codex-version": advert.attrib["applied-to-codex-version"],
            "article-count": str(len(advert.xpath("//advert-art"))),
        })

        affected_laws = advert.find("affected-laws")
        if affected_laws is not None:
            advert_entry.append(affected_laws)

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
