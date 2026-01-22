import dateparser
from datetime import datetime
from lagasafn.advert.intent.parsers import parse_intents_by_text_analysis
from lagasafn.advert.intent.parsers import parse_intents_by_ai
from lagasafn.advert.tracker import AdvertTracker
from lagasafn.exceptions import AdvertParsingException
from lagasafn.exceptions import IntentParsingException
from lagasafn.models.law import LawManager
from lagasafn.utils import determine_month
from lagasafn.utils import get_all_text
from lagasafn.utils import super_iter
from lagasafn.utils import is_roman
from lagasafn.settings import FEATURES
from lxml.builder import E
from lxml.etree import _Element
import re
import roman


def parse_description(tracker: AdvertTracker):
    if tracker.nodes.current.tag != "h1":
        return False

    description = get_all_text(tracker.nodes.current)

    tracker.xml.append(E("description", description))

    tracker.detect_affected_law(description, tracker.xml)

    next(tracker.nodes)

    return True


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


def parse_empty(tracker: AdvertTracker, non_empty_if_next: str = r""):
    # Ignored.
    node = tracker.current_node()
    if not (
        (node.text is None or node.text.strip() == "")
        and node.tail.strip() == ""
        and len(node.getchildren()) == 0
    ):
        return False

    # Sometimes empty nodes denote the end of an article, and sometimes it
    # belongs inside the content of something being parsed. To distinguish
    # between these, the argument `non_empty_if_next` is provided, which takes
    # a regex. If that regex matches the line after the empty space, then we'll
    # still call this non-empty, so that the empty space can be handled by the
    # calling parsing function accordingly.
    #
    # Occurs in adverts 138/2024 and 140/2024.
    text = get_all_text(tracker.nodes.peek())
    if len(non_empty_if_next) and re.match(non_empty_if_next, text) is not None:
        return False

    next(tracker.nodes)

    return True


def parse_article_nr_title(tracker: AdvertTracker):

    node = tracker.current_node()

    text = get_all_text(node)
    match = re.match(r"(\d+)\. gr\.$", text)
    if match is None:
        return False

    # Determine the article number.
    art_nr = match.groups()[0]

    # Create the article.
    # TODO: The article should only be created if it doesn't already exist.
    # This requires a bit of refactoring, so that instead of files being
    # created every time that processing takes place, they are read and
    # modified if they already exist.
    art = E("advert-art", {"nr": art_nr})

    if tracker.targets.chapter is not None:
        tracker.targets.chapter.append(art)
    else:
        tracker.xml.append(art)
    tracker.targets.art = art

    # We'll start by gathering all the content of the article into the node for
    # later handling.
    original = E("original", node.tail)
    art.append(original)

    # Declare what the article supposedly affects. Note that there are articles
    # which alter many laws, which this configuration won't know about, but
    # instead the `intent` elements will.
    if "law-nr" in tracker.affected and "law-year" in tracker.affected:
        original.attrib["affected-law-nr"] = tracker.affected["law-nr"]
        original.attrib["affected-law-year"] = tracker.affected["law-year"]

    next(tracker.nodes)
    while (
        not parse_empty(tracker, non_empty_if_next=r"[a-z]\. \(.*\)$")
        # On occasion, articles aren't properly ended with an empty node, so we
        # need to check here if an article or chapter immediately follows.
        and re.match(r"(\d+)\. gr\.$", get_all_text(tracker.current_node())) is None
        and re.match(r"([IVXLCDM]+)\. KAFLI", get_all_text(tracker.current_node()))
        is None
    ):
        original.append(tracker.current_node())
        next(tracker.nodes)

    # TODO: Remove feature knob when functionality is complete.
    if FEATURES["PARSE_INTENTS"]:

        existing_intents = art.find("intents")
        if existing_intents is None:

            try:
                parse_intents_by_text_analysis(tracker, original)
            except IntentParsingException:

                # **Maybe** we want to try AI here?
                if FEATURES["PARSE_INTENTS_AI"]:
                    # NOTE: The AI parsing currently returns `intents` as XML
                    # instead of `tracker`'s content being modified by the
                    # parsing function itself.
                    intents = parse_intents_by_ai(tracker, original)
                    art.append(intents)
                else:
                    raise

            print(".", end="", flush=True)

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

    chapter = E(
        "advert-chapter", {"nr": str(nr), "nr-type": "roman", "roman-nr": roman_nr}
    )

    next(tracker.nodes)

    description = get_all_text(tracker.current_node())
    chapter.append(E("description", description))

    tracker.detect_affected_law(description, chapter)

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
    if tracker.targets.temp_clause.attrib["temp-clause-type"] == "advert-art":
        tracker.targets.temp_clause.attrib["temp-clause-type"] = "advert-chapter"
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
    temp_clause = E(
        "temp-clause", {"temp-clause-type": "advert-art", "processed": "false"}
    )

    tracker.targets.temp_clause = temp_clause
    tracker.xml.append(temp_clause)

    # We'll need to parse the content differently depending on whether the
    # temporary clause contains articles (labelled "I.", "II.", "III." etc. or
    # not, and this keeps track of that.
    contains_articles = False

    next(tracker.nodes)
    while not parse_empty(tracker):
        if parse_temporary_clause_article(tracker):
            contains_articles = True
            continue

        if not contains_articles:
            temp_clause.append(tracker.current_node())
            next(tracker.nodes)
            continue

        break

    tracker.targets.temp_clause = None

    return True


def parse_signature_confirmation(tracker: AdvertTracker):
    text = get_all_text(tracker.current_node())
    if not (
        text.startswith("Gjört á Bessastöðum") or text.startswith("Gjört í Reykjavík")
    ):
        return False

    tracker.xml.append(E("signed-when", text))

    next(tracker.nodes)

    return True


def parse_parliamentary_approval(tracker: AdvertTracker):
    text = get_all_text(tracker.current_node())
    if not text.startswith("Samþykkt á Alþingi "):
        return False

    tracker.xml.append(E("approved-by-parliament-when", text))

    # NOTE: No need for `next(tracker.nodes)` since there is no more content.

    return True


def parse_advert(doc_info: dict, xml_remote: _Element):

    # Vestigial attribute, retained to make diffing easier during development.
    # Should be removed at some point.
    record_id = "00000000-0000-4000-0000-000000000000"

    tracker = AdvertTracker(E("advert", {"type": "law", "record-id": record_id}))

    nr, year = [int(p) for p in doc_info["law_identifier"].split("/")]

    # Figure out the date that this document wash published. We remove the
    # timezone info because other parts of the program assume timezone-naive
    # variables, but everything we do here is in UTC.
    published_date = dateparser.parse(doc_info["law_time_published"]).replace(
        tzinfo=None
    )

    # Fill gathered information into XML.
    tracker.xml.attrib["year"] = str(year)
    tracker.xml.attrib["nr"] = str(nr)
    tracker.xml.attrib["published-date"] = published_date.strftime("%Y-%m-%d")
    tracker.xml.attrib["applied-to-codex-version"] = LawManager.codex_version_at_date(
        published_date
    )

    tracker.nodes = super_iter(xml_remote.getchildren())
    next(tracker.nodes)

    while True:
        if parse_description(tracker):
            continue
        if parse_break(tracker):
            continue
        if parse_president_declaration(tracker):
            continue
        if parse_empty(tracker):
            continue
        if parse_article_nr_title(tracker):
            continue
        if parse_chapter_nr_title(tracker):
            continue
        if parse_temporary_clause(tracker):
            continue

        # These two are siblings but mutually exclusive, depending on whether
        # the document is from Parliament or the Gazette. The Gazette version
        # should probably be removed (`parse_signature_confirmation`).
        if parse_parliamentary_approval(tracker):
            break
        if parse_signature_confirmation(tracker):
            break

        node = tracker.current_node()

        # This is a good debugging point.
        #text = get_all_text(node)
        #print()
        #print("Text: %s" % text)
        #import ipdb; ipdb.set_trace()

        raise AdvertParsingException("Can't parse element: %s" % node)

    return tracker.xml
