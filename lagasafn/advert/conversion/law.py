from lagasafn.exceptions import AdvertParsingException
from lagasafn.utils import super_iter
from lxml.builder import E
import re


def get_all_text(node):
    """
    A function for retrieving the text content of an element and all of its
    descendants. Some special regex needed because of content peculiarities.

    FIXME: This concatenates strings with a `<br/>` between them. It's not a
    problem yet, but it will become one. Probably requires rewriting from
    scratch to fix that.
    """
    # Get the text
    result = "".join([re.sub(r"^\n *", " ", t) for t in node.itertext()])

    # Remove non-breaking space.
    result = result.replace("\xa0", " ")

    # Consolidate spaces.
    while result.find("  ") > -1:
        result = result.replace("  ", " ")

    # Strip the result.
    result = result.strip()

    return result


def parse_break(node):
    # Breaks are ignored.
    return node.tag == "br"


def parse_president_declaration(node):
    text = get_all_text(node)
    return text.startswith("Forseti Íslands gjörir kunnugt") or text.startswith(
        "Handhafar valds forseta Íslands samkvæmt 8. gr. stjórnarskrárinnar"
    )


def parse_empty(node):
    # Ignored.
    return node.text.strip() == "" and len(node.getchildren()) == 0


def parse_article_nr_title(node, nodes, xml_advert):
    text = get_all_text(node)
    match = re.match(r"(\d+)\. gr\.", text)
    if match is None:
        return False

    # Make and add the article node.
    art_nr = match.groups()[0]
    art = E(
        "art",
        {
            "nr": art_nr,
            "processed": "false",
        },
    )
    xml_advert.append(art)

    # We'll start by gathering all the content of the article into the node for
    # later handling.
    original = E("original")
    art.append(original)

    while True:
        subnode = next(nodes)

        if parse_empty(subnode):
            break

        original.append(subnode)

    return True


def parse_signature_confirmation(node):
    text = get_all_text(node)
    return text.startswith("Gjört á Bessastöðum") or text.startswith(
        "Gjört í Reykjavík"
    )


def convert_advert_law(xml_remote):

    # Container for information about what's being affected at any given point
    # in time. For example, when we run into "2. mgr.", this might contain
    # information about in which article, and subsequently in which law, based
    # on previously parsed content.
    #
    # This information doesn't always pop in the same places during the
    # parsing. For example, which law is being changed can show up in the name
    # of the advert, or in the name of a chapter.
    #
    # We will record as much about this as we can into each element in the
    # resulting advert XML.
    affected = {}

    # Bare-bones result document.
    xml_advert = E("advert", {"type": "law"})

    # Figure out nr/year from content.
    raw_nr_year = xml_remote.xpath(
        "/div/table/tbody/tr[@class='advertText']/td[@align='left']"
    )[0].text.strip()
    nr, year = re.findall(r"Nr\. (\d{1,3})\/(\d{4})", raw_nr_year)[0]
    del raw_nr_year

    # Find description.
    description = xml_remote.xpath("/div/table/tbody/tr[@class='advertType2']/td")[
        0
    ].text

    # Figure out which laws are being changed.
    found_in_description = re.findall(r"nr\. (\d{1,3})\/(\d{4})", description)
    if len(found_in_description) > 1:
        # This never happened between 2024-04-12 and 2025-01-13 at least, but
        # is placed here to prevent mistakes in the future.
        raise AdvertParsingException(
            "Don't know how to handle more than one law number in advert title"
        )
    elif len(found_in_description) == 1:
        affected["law-nr"], affected["law-year"] = found_in_description[0]

    # Fill gathered information into XML.
    xml_advert.attrib["year"] = year
    xml_advert.attrib["nr"] = nr
    xml_advert.append(E("description", description))

    nodes = xml_remote.xpath(
        "/div/table[position() = 2]/tbody/tr[@class='advertText']/td[@class='advertTD']"
    )[0].getchildren()
    nodes = super_iter(nodes)
    while True:
        node = next(nodes)
        if parse_break(node):
            continue
        if parse_president_declaration(node):
            continue
        if parse_empty(node):
            continue
        if parse_article_nr_title(node, nodes, xml_advert):
            continue
        if parse_signature_confirmation(node):
            break

        # This is a good debugging point.
        # text = get_all_text(node)
        # print()
        # print("Text: %s" % text)
        # import ipdb; ipdb.set_trace()

        raise AdvertParsingException("Can't parse element: %s" % node)

    return xml_advert
