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

    FIXME: There is another function, `lagasafn.utils.convert_to_text` which
    was designed for a different purpose. These two should be merged and fixed
    so that they work with anything in the entire project.
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
    if tracker.current_node().tag != "br":
        return False

    next(tracker.nodes)

    return True


def parse_president_declaration(tracker):
    text = get_all_text(tracker.current_node())
    if not (
        text.startswith("Forseti Íslands gjörir kunnugt")
        or text.startswith(
            "Handhafar valds forseta Íslands samkvæmt 8. gr. stjórnarskrárinnar"
        )
    ):
        return False

    next(tracker.nodes)

    return True


def parse_empty(tracker: AdvertTracker):
    # Ignored.
    node = tracker.current_node()
    if not (
        node.text.strip() == ""
        and node.tail.strip() == ""
        and len(node.getchildren()) == 0
    ):
        return False

    next(tracker.nodes)

    return True


def parse_article_nr_title(tracker: AdvertTracker):

    node = tracker.current_node()

    text = get_all_text(node)
    match = re.match(r"(\d+)\. gr\.$", text)
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

    next(tracker.nodes)
    while (
        not parse_empty(tracker)
        # On occasion, articles aren't properly ended with an empty node, so we
        # need to check here if an article immediately follows.
        and re.match(r"(\d+)\. gr\.$", get_all_text(tracker.current_node())) is None
    ):
        original.append(tracker.current_node())
        next(tracker.nodes)

    return True


def parse_chapter_nr_title(tracker):
    text = get_all_text(tracker.current_node())

    if not text.endswith("KAFLI"):
        return False

    roman_nr = text[: text.index(".")]
    if not is_roman(roman_nr):
        raise AdvertParsingException(
            "Expected Roman numeral when parsing chapter: %s" % text
        )

    nr = roman.fromRoman(roman_nr)

    chapter = E("chapter", {"nr": str(nr), "nr-type": "roman", "roman-nr": roman_nr})

    next(tracker.nodes)
    description = get_all_text(tracker.current_node())
    if description.startswith("Breyting á lögum"):
        nrs_found = re.findall(r"nr\. (\d{1,3})\/(\d{4})", description)
        if len(nrs_found) > 1:
            raise AdvertParsingException(
                "Can't deal with more than one law in chapter description."
            )
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


def parse_temporary_clause_article(tracker: AdvertTracker):
    text = get_all_text(tracker.current_node())
    if not (
        tracker.targets.temp_clause is not None
        and "." in text
        and is_roman(text[: text.index(".")])
    ):
        return False

    roman_nr = text[: text.index(".")]
    nr = roman.fromRoman(roman_nr)

    # We have retroactively figured out that this is a temporary article inside
    # a temporary chapter. We must retro-actively set the type of the chapter
    if tracker.targets.temp_clause.attrib["temp-clause-type"] == "art":
        tracker.targets.temp_clause.attrib["temp-clause-type"] = "chapter"
        del tracker.targets.temp_clause.attrib["processed"]

    temp_art = E("temp-art", {"nr": str(nr), "nr-type": "roman", "roman-nr": roman_nr})

    tracker.targets.temp_clause.append(temp_art)

    next(tracker.nodes)
    while not parse_empty(tracker):
        temp_art.append(tracker.current_node())
        next(tracker.nodes)

    return True


def parse_temporary_clause(tracker: AdvertTracker):
    """
    FIXME: Distinguishing temporary clauses that are expressed in chapters and
    those that are expressed in articles, is an unsolved problem. This
    currently just shoves the whole thing into a node and leaves it at that.
    """
    text = get_all_text(tracker.current_node())
    if text != "Ákvæði til bráðabirgða.":
        return False

    # The default type is `art` because we will only find out later if this
    # temporary clause contains several articles, and is in fact a chapter, or
    # if it only contains direct content, in which case it's an article.
    temp_clause = E("temp-clause", {"temp-clause-type": "art", "processed": "false"})

    tracker.targets.temp_clause = temp_clause
    tracker.xml.append(temp_clause)

    next(tracker.nodes)
    while not parse_empty(tracker):
        if parse_temporary_clause_article(tracker):
            continue

        temp_clause.append(tracker.current_node())
        next(tracker.nodes)

    tracker.targets.temp_clause = None

    return True


def parse_signature_confirmation(tracker: AdvertTracker):
    text = get_all_text(tracker.current_node())
    if not (
        text.startswith("Gjört á Bessastöðum") or text.startswith("Gjört í Reykjavík")
    ):
        return False

    next(tracker.nodes)

    return True


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

    next(tracker.nodes)
    while True:
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
        if parse_temporary_clause(tracker):
            continue

        # This is a good debugging point.
        node = tracker.current_node()
        text = get_all_text(node)
        print()
        print("Text: %s" % text)
        import ipdb; ipdb.set_trace()

        raise AdvertParsingException("Can't parse element: %s" % node)

    return tracker.xml
