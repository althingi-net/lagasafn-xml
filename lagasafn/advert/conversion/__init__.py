from copy import deepcopy
from lagasafn.constants import ADVERT_DIR
from lagasafn.constants import ADVERT_INDEX_FILENAME
from lagasafn.constants import ADVERT_REMOTES_DIR
from lagasafn.advert.conversion.law import convert_advert_law
from lagasafn.utils import write_xml
from lxml import etree
from lxml.builder import E
from os import listdir
from os import path
import re


def convert_adverts():
    """
    Converts all remote adverts into proper XML.
    """
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
        xml_advert = convert_advert_law(xml_remote)
    else:
        print(" skipping (unsupported type '%s')" % advert_type)
        return

    write_xml(xml_advert, path.join(ADVERT_DIR, "%d.%d.advert.xml" % (year, nr)))

    print(" done")


def create_index():
    """
    Creates an index of adverts that exist in XML form.
    """

    advert_index = E("advert-index")

    for advert_filename in listdir(ADVERT_DIR):
        fullpath = path.join(ADVERT_DIR, advert_filename)
        advert = etree.parse(fullpath).getroot()

        advert_entry = E("advert-entry", {
            "type": advert.attrib["type"],
            "year": advert.attrib["year"],
            "nr": advert.attrib["nr"],
            "published-date": advert.attrib["published-date"],
        })

        advert_index.append(advert_entry)

    # Sort index for consistency's sake.
    advert_index[:] = sorted(
        advert_index,
        key=lambda n: (int(n.attrib["year"]), int(n.attrib["nr"])),
        reverse=True
    )

    write_xml(advert_index, ADVERT_INDEX_FILENAME)
