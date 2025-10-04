import requests
from lagasafn.chaostemple.service import law_documents
from lagasafn.constants import ADVERT_DIR
from lagasafn.constants import ADVERT_FILENAME
from lagasafn.constants import ADVERT_ORIGINAL_DIR
from lagasafn.constants import ADVERT_ORIGINAL_FILENAME
from lagasafn.constants import ADVERT_INDEX_FILENAME
from lagasafn.advert.parsers import parse_advert
from lagasafn.exceptions import AdvertException
from lagasafn.exceptions import IntentParsingException
from lagasafn.exceptions import ReferenceParsingException
from lagasafn.settings import CHAOSTEMPLE_URL
from lagasafn.utils import write_xml
from lxml import etree
from lxml.etree import _Element
from lxml.builder import E
from os import listdir
from os import makedirs
from os import unlink
from os import path


def convert_adverts(requested_identifiers: list[str] = []):
    """
    Converts all remote adverts into proper XML.
    """

    doc_infos = []

    # Map identifiers to documents for selection.
    r_docs = law_documents()
    for r_doc in r_docs:
        if r_doc["law_identifier"] == "not-found":
            continue

        if (
            len(requested_identifiers) == 0
            or (
                len(requested_identifiers) > 0
                and r_doc["law_identifier"] in requested_identifiers
            )
        ):
            doc_infos.append(r_doc)
            if r_doc["law_identifier"] in requested_identifiers:
                requested_identifiers.remove(r_doc["law_identifier"])

    if len(requested_identifiers) > 0:
        raise AdvertException("Adverts %s not found: %s" % ",".join(requested_identifiers))

    for doc_info in doc_infos:
        convert_advert(doc_info)


def convert_advert(doc_info: dict):
    """
    Converts a single remote advert XML to a proper advert XML.
    """

    nr, year = [int(p) for p in doc_info["law_identifier"].split("/")]

    print("Converting %s" % doc_info["law_identifier"])

    # Get the HTML content and convert into XML.
    response = requests.get("%s%s" % (
        CHAOSTEMPLE_URL,
        doc_info["html_content_path"]
    ))
    response.raise_for_status()
    xml_remote = etree.fromstring(response.text)

    # Write down the original for easier diffing and such during development.
    makedirs(ADVERT_ORIGINAL_DIR, exist_ok=True)
    write_xml(xml_remote, ADVERT_ORIGINAL_FILENAME % (year, nr), skip_strip=True)

    out_filename = ADVERT_FILENAME % (year, nr)
    try:
        xml_advert = parse_advert(doc_info, xml_remote)
        write_xml(xml_advert, out_filename)
        print(" done")
    except (IntentParsingException, ReferenceParsingException) as ex:
        # Delete the file if it already existed, so that we can tell the
        # difference in `git status` and `git diff`.
        try:
            unlink(out_filename)
        except FileNotFoundError:
            pass

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
