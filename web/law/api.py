from core.exceptions import ReferenceParsingException
from core.utils import make_xpath
from django.http import HttpResponse
from law.exceptions import LawException
from law.models import Law
from lxml import etree
from lxml.etree import Element
from ninja import File
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.files import UploadedFile
from typing import List

api = NinjaAPI()


def convert_to_text(elements: List[Element]):
    result = ""

    # Cluck together all text in all descendant nodes.
    for element in elements:
        for child in element.iterdescendants():
            if child.text is not None:
                result += child.text.strip() + " "
        result = result.strip() + "\n"

    # Remove double spaces that may result from concatenation above.
    while "  " in result:
        result = result.replace("  ", " ")

    return result


@api.get("parse-reference/")
def parse_reference(request, reference):
    # TODO: Sanity check on reference to prevent garbage input.
    # ...

    law_nr = None
    law_year = None

    # Make sure there are no stray spaces in reference. They often appear when
    # copying from PDF documents.
    reference = reference.strip()
    while reference.find("  ") > -1:
        reference = reference.replace("  ", " ")

    # Turn reference into words that we will parse one by one, but backwards,
    # because human-readable addressing has the most precision in the
    # beginning ("1. tölul. 2. gr. laga nr. 123/2000") but data addressing the
    # other way around.
    words = reference.split(" ")
    words.reverse()

    # Parse law number and year if they exist.
    if "/" in words[0] and words[1] == "nr.":
        law_nr, law_year = words[0].split("/")
        words.pop(0)
        words.pop(0)

    # Map of known human-readable separators and their mappings into elements.
    known_seps = {
        "gr.": "art",
    }

    # Look for a known separator, forwarding over the possible name of the law
    # and removing it, since it's not useful. This disregards the law's name.
    known_sep_found = False
    while not known_sep_found:
        if words[0] in known_seps:
            known_sep_found = True
        else:
            words.pop(0)

    # At this point the remaining words should begin with something we can
    # process into a location inside a document.

    # Remove trailing dots from the remaining words, since they'll only get in
    # the way from now on, but may end up a law's name above.
    words = [w.strip(".") for w in words]

    # Create selector.
    try:
        xpath = make_xpath(words)
    except ReferenceParsingException as ex:
        raise HttpError(500, "Confused by: %s" % ex.args[0])

    # Also return the segment.
    segment = get_segment(request, law_nr, law_year, xpath)

    return {
        "xpath": xpath,
        "law_nr": law_nr,
        "law_year": law_year,
        "segment": segment,
        # "reference": reference,
        # "trails": trails,  # Debug
        # "words": words,  # Debug
    }


@api.get("get-segment/")
def get_segment(request, law_nr: int, law_year: int, xpath: str):
    try:
        law = Law("%s/%s" % (law_nr, law_year))
    except LawException as ex:
        raise HttpError(400, ex.args[0])

    elements = law.xml().xpath(xpath)

    if len(elements) == 0:
        raise HttpError(404, "Could not find requested element.")

    text_result = convert_to_text(elements)
    xml_result = [
        etree.tostring(
            element, pretty_print=True, xml_declaration=False, encoding="utf-8"
        ).decode("utf-8")
        for element in elements
    ]

    return {
        "text_result": text_result,
        "xml_result": xml_result,
    }


@api.post("normalize/")
def normalize(request, input_file: UploadedFile = File(...)):
    """
    Takes an uploaded XML law and makes sure that it is formatted in the same
    way as the codex. Useful for comparison.
    """

    input_data = input_file.read()

    xml_doc = etree.fromstring(input_data)

    # Strip all elements in document.
    for element in xml_doc.iter():
        # If the element has text, strip leading and trailing whitespace
        if element.text:
            element.text = element.text.strip()

        # If the element has tail, strip leading and trailing whitespace
        if element.tail:
            element.tail = element.tail.strip()

    # Re-encode `minister-clause` because it's actually HTML with some
    # exporting quirks (from the original HTML-exporting software) that we
    # also imitate.
    minister_clause = xml_doc.find("minister-clause")
    encoded_clause = ""
    for child in minister_clause:
        encoded_clause += etree.tostring(child, encoding="unicode")
    encoded_clause = encoded_clause.replace(">", "> ")
    encoded_clause = encoded_clause.replace("<", " <")
    encoded_clause = encoded_clause.replace("  ", " ").strip()
    for child in list(minister_clause):
        minister_clause.remove(child)
    minister_clause.text = encoded_clause

    # For details, see comparable section in `lagasafn-xml` project.
    import xml.dom.minidom

    xml = xml.dom.minidom.parseString(
        etree.tostring(
            xml_doc, pretty_print=True, xml_declaration=True, encoding="utf-8"
        ).decode("utf-8")
    )
    normalized_file = xml.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")

    return HttpResponse(normalized_file, content_type="text/xml")
