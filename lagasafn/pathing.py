import roman
from lagasafn.constants import XML_FILENAME
from lagasafn.exceptions import NoSuchElementException, NoSuchLawException, ReferenceParsingException
from lagasafn.utils import convert_to_text
from lagasafn.utils import is_roman
from lxml import etree
from typing import List


def make_xpath_from_node(node):
    """
    Generates a distinct XPath location for a given node, including the node's
    names and attributes.

    IMPORTANT: This function must never return a string with double quotes,
    because it will be stored in XML attributes which will themselves be using
    double quotes as value delimiters.
    """

    # Initialize a list to store parts of the XPath as we build it.
    xpath_parts = []

    while node is not None and node.getparent() is not None:
        # Extract and format the current node's attributes into XPath syntax.
        attrib_parts = []
        for wanted_attrib in ["nr", "ultimate-nr", "sub-paragraph-nr", "chapter-type"]:
            if wanted_attrib in node.attrib:
                # IMPORTANT: Single quotes for values, not double quotes.
                attrib_parts.append(
                    "@%s='%s'" % (wanted_attrib, node.attrib[wanted_attrib])
                )

        attributes_xpath = " and ".join(attrib_parts)

        # Construct XPath part for current node, with attributes if any.
        if attributes_xpath:
            xpath_part = f"{node.tag}[{attributes_xpath}]"
        else:
            siblings = [e for e in node.getparent() if e.tag == node.tag]
            place_among_siblings = siblings.index(node) + 1
            xpath_part = "%s[%d]" % (node.tag, place_among_siblings)

        # Insert the constructed XPath part at the beginning of the list.
        xpath_parts.insert(0, xpath_part)

        # Move to the parent node for the next iteration.
        node = node.getparent()

    # Join all parts of the XPath with slashes to form the final XPath string.
    return "/".join(xpath_parts)


def make_xpath_from_inner_reference(inner_reference: str):

    # Turn the inner reference into a a reversed list that's easier to deal
    # with word-by-word.
    words = inner_reference.split(" ")
    words.reverse()

    # Remove trailing dots, since they'll only get in the way.
    words = [w.strip(".") for w in words]

    def first_or_blank(some_list):
        """
        Utility function so that we can do this inline.
        """
        return some_list[0] if len(some_list) else ""

    def real_number(input_number):
        """
        Takes a number that could be a Roman numeral or whatever else, and
        returns the proper number to look up by.
        """
        number = input_number

        # Convert from Roman numeral if appropriate.
        if is_roman(number):
            number = roman.fromRoman(number)

        return number

    xpath = ""

    # This dictinoary contains translates from the actual words used in an
    # inner reference, into tag names used in the XML.
    translations = {
        "gr": "art",
        "tölul": "numart",
        "mgr": "subart",
        "kafli": "chapter",
        "kafla": "chapter",
    }

    while len(words):

        # Initialize.
        ent_type = ""
        ent_numbers = []

        word = words.pop(0)

        # NOTE: Don't forget to implement support for things like "3. gr. a".
        # These are not implemented yet, but should be done here.

        if word[-4:] == "-lið":
            ent_type = "*[self::numart or self::art-chapter]"
            ent_numbers.append(word[: word.find("-lið")])
        elif word in translations.keys():
            ent_type = translations[word]

            ent_numbers.append(real_number(words.pop(0)))

            # All of these combinatory words result in us looking up all of
            # them, so they are all in effect "or", for our purposes.
            if first_or_blank(words) in ["og", "eða", "og/eða"]:
                words.pop(0)
                ent_numbers.append(real_number(words.pop(0)))
        else:
            # Oh no! We don't know what to do!
            raise ReferenceParsingException(word)

        # Assuming something came of this...
        if len(ent_type):
            # ... construct the XPath bit and add it to the result!
            xpath += "//%s[%s]" % (
                ent_type,
                " or ".join(["@nr='%s'" % n for n in ent_numbers]),
            )

    return xpath


def get_segment(law_nr: str, law_year: int, xpath: str):
    try:
        xml = etree.parse(XML_FILENAME % (law_year, law_nr)).getroot()
    except:
        raise NoSuchLawException()

    elements = xml.xpath(xpath)

    if len(elements) == 0:
        raise NoSuchElementException()

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
