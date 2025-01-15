from lagasafn.advert.conversion.tracker import AdvertTracker
from lagasafn.exceptions import AdvertParsingException
from lagasafn.utils import super_iter
from lagasafn.utils import is_roman
from lxml.builder import E
from lxml.etree import _Element
import re
import roman


def get_all_text(node: _Element):
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


def parse_break(tracker: AdvertTracker):
    # Breaks are ignored.
    return tracker.current_node().tag == "br"


def parse_president_declaration(tracker):
    text = get_all_text(tracker.current_node())
    return text.startswith("Forseti Íslands gjörir kunnugt") or text.startswith(
        "Handhafar valds forseta Íslands samkvæmt 8. gr. stjórnarskrárinnar"
    )


def parse_empty(tracker: AdvertTracker):
    # Ignored.
    node = tracker.current_node()
    return node.text.strip() == "" and len(node.getchildren()) == 0


def parse_article_nr_title(tracker: AdvertTracker):

    node = tracker.current_node()

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

    if tracker.targets.chapter is not None:
        tracker.targets.chapter.append(art)
    else:
        tracker.xml.append(art)

    # We'll start by gathering all the content of the article into the node for
    # later handling.
    original = E("original")
    art.append(original)

    while True:
        subnode = next(tracker.nodes)

        if parse_empty(tracker):
            break

        original.append(subnode)

    return True


def parse_chapter_nr_title(tracker):
    text = get_all_text(tracker.current_node())

    if not text.endswith("KAFLI"):
        return False

    roman_nr = text[:text.index(".")]
    if not is_roman(roman_nr):
        raise AdvertParsingException("Expected Roman numeral when parsing chapter: %s" % text)

    nr = roman.fromRoman(roman_nr)

    chapter = E("chapter", { "nr": str(nr), "nr-type": "roman", "roman-nr": roman_nr })

    next(tracker.nodes)
    description = get_all_text(tracker.current_node())
    if description.startswith("Breyting á lögum"):
        nrs_found = re.findall(r"nr\. (\d{1,3})\/(\d{4})", description)
        if len(nrs_found) > 1:
            raise AdvertParsingException("Can't deal with more than one law in chapter description.")
        elif len(nrs_found) == 0:
            raise AdvertParsingException("Could not find affected law in chapter name.")

        tracker.affected["law-nr"], tracker.affected["law-year"] = nrs_found[0]

        next(tracker.nodes)

    tracker.targets.chapter = chapter
    tracker.xml.append(chapter)

    while True:
        if parse_article_nr_title(tracker):
            continue
        break

    tracker.targets.chapter = None

    return True


def parse_signature_confirmation(tracker: AdvertTracker):
    text = get_all_text(tracker.current_node())
    return text.startswith("Gjört á Bessastöðum") or text.startswith(
        "Gjört í Reykjavík"
    )


def convert_advert_law(xml_remote):

    tracker = AdvertTracker(E("advert", {"type": "law"}))

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

    # Figure out which laws are being changed. If nothing is found, then
    # probably multiple laws are being changed and this information will be
    # inside chapters.
    found_in_description = re.findall(r"nr\. (\d{1,3})\/(\d{4})", description)
    if len(found_in_description) > 1:
        # This never happened between 2024-04-12 and 2025-01-13 at least, but
        # is placed here to prevent mistakes in the future.
        raise AdvertParsingException(
            "Don't know how to handle more than one law number in advert title"
        )
    elif len(found_in_description) == 1:
        tracker.affected["law-nr"], tracker.affected["law-year"] = found_in_description[
            0
        ]

    # Fill gathered information into XML.
    tracker.xml.attrib["year"] = year
    tracker.xml.attrib["nr"] = nr
    tracker.xml.append(E("description", description))

    nodes = xml_remote.xpath(
        "/div/table[position() = 2]/tbody/tr[@class='advertText']/td[@class='advertTD']"
    )[0].getchildren()

    tracker.nodes = super_iter(nodes)

    while True:
        node = next(tracker.nodes)
        if parse_break(tracker):
            continue
        if parse_president_declaration(tracker):
            continue
        if parse_empty(tracker):
            continue
        if parse_article_nr_title(tracker):
            continue
        if parse_signature_confirmation(tracker):
            break
        if parse_chapter_nr_title(tracker):
            continue

        # This is a good debugging point.
        # text = get_all_text(node)
        # print()
        # print("Text: %s" % text)
        # import ipdb; ipdb.set_trace()

        raise AdvertParsingException("Can't parse element: %s" % node)

    return tracker.xml
