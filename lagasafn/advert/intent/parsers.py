"""
NOTE: The text-analysis parsing functions in here entail **a lot** of
repetitions and distinctions that are completely unnecessary, but this is
currently by design.

It will remain so while we establish every possible permutation of every single
way to change things, so that we can map out where exactly the distinctions are
important and where they are not. At that point, these functions will be joined
together appropriately and the redundancy reduced.

Please don't fix anything here without speaking with the original author first.
"""

import dateparser
import json
import re
import roman
from copy import deepcopy
from lagasafn.advert.tracker import AdvertTracker
from lagasafn.advert.intent.tracker import IntentTracker
from lagasafn.constants import ICELANDIC_DATE_REGEX
from lagasafn.constructors import construct_appendix
from lagasafn.constructors import construct_node
from lagasafn.constructors import construct_temp_chapter_from_art
from lagasafn.constructors import construct_sens
from lagasafn.contenthandlers import add_sentences
from lagasafn.contenthandlers import analyze_art_name
from lagasafn.contenthandlers import analyze_chapter_nr_title
from lagasafn.contenthandlers import separate_sentences
from lagasafn.exceptions import IntentParsingException
from lagasafn.exceptions import NoSuchLawException
from lagasafn.models.intent import IntentModelList
from lagasafn.references import get_law_name_permutations
from lagasafn.utils import generate_legal_reference
from lagasafn.utils import get_all_text
from lagasafn.utils import is_roman
from lagasafn.utils import remove_garbage
from lagasafn.utils import write_xml
from lxml.builder import E
from lxml.etree import _Element
from openai import OpenAI


def parse_intents_by_ai(advert_tracker: AdvertTracker, original: _Element):
    intents = []

    with open("data/prompts/intent-parsing.md") as r:
        prompt = r.read()

        # Fill in necessary information.
        # TODO: Replace this with proper Django templating.
        prompt = prompt.replace("{affected_law_nr}", advert_tracker.affected["law-nr"])
        prompt = prompt.replace(
            "{affected_law_year}", advert_tracker.affected["law-year"]
        )

    xml_text = write_xml(original)

    client = OpenAI()

    completion = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": "Meðfylgjandi XML skjal 'remote.xml' er hér: %s" % xml_text,
            },
        ],
        response_format=IntentModelList,
    )

    items = json.loads(completion.choices[0].message.to_dict()["content"])["items"]

    intents = E("intents")
    for item in items:
        # Construct an XML element from the intent model.
        intent = E("intent")
        intents.append(intent)
        for key in item.keys():
            # Respecting XML conventions using dashes instead of underscores.
            element_name = key.replace("_", "-")
            value = item[key]

            intent.append(E(element_name, value))

    return intents


def parse_x_laganna_ordast_svo(tracker: IntentTracker):
    match = re.match(
        r"(.+) (laganna|í lögunum)(, sem hefur fyrirsögnina (.+),)? orðast svo(, ásamt fyrirsögn)?: ?(.+)?",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, name, _, text_to = match.groups()

    intent = tracker.make_intent("replace", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "art":
        # The function `parse_inner_art` won't be able to determine the type of
        # content, except as determined by `prefilled`. It relies on us only
        # calling it when we know that we expect an article.

        prefilled = {
            "nr": existing[0].attrib["nr"],
            "nr_title": existing[0].find("nr-title").text,
        }

        parse_inner_art(tracker, prefilled)

    elif len(existing) == 1 and existing[0].tag == "subart":

        # It may very well happen that a `subart` will be replaced with inline
        # content at some point. In that case, we should use `construct_node`
        # here instead of `parse_inner_art_subart`.
        if text_to is not None:
            raise IntentParsingException(
                "Unimplemented: Inline subart content at address: %s" % address
            )

        next(tracker.lines)
        parse_inner_art_subart(tracker, {"nr": existing[0].attrib["nr"]})

    elif len(existing) == 1 and existing[0].tag == "numart":
        tracker.targets.inner.append(construct_node(existing[0], text_to, nr_change=0))

    elif len(existing) == 1 and existing[0].tag == "name":
        tracker.targets.inner.append(E("name", text_to))

    elif len(existing) == 1 and existing[0].tag == "sen":
        for sen in construct_sens(existing[0], text_to):
            tracker.targets.inner.append(sen)

    elif len(existing) == 1 and existing[0].tag == "chapter":
        tracker.inner_targets.chapter = construct_node(
            existing[0], name=name, nr_change=0
        )

        while parse_inner_art(tracker):
            pass

        tracker.targets.inner.append(tracker.inner_targets.chapter)
        tracker.inner_targets.chapter = None

    else:
        raise IntentParsingException(
            "Don't know how to replace at address: %s" % address
        )

    tracker.targets.inner = None
    tracker.intents.append(intent)

    return True


def parse_x_laganna_verdur(tracker: IntentTracker):
    # NOTE: Currently only known to happen when a law's name is changed but may
    # very well be expanded if the same phrasingn gets used for other things.
    match = re.match(r"(.+) laganna verður: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("replace", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    intent.append(inner)
    tracker.intents.append(intent)

    if len(existing) == 1 and existing[0].tag == "name":
        inner.append(E("name", text_to))
    else:
        raise IntentParsingException(
            "Don't know how to replace at address: %s" % address
        )

    return True


def parse_x_laganna_fellur_brott(tracker: IntentTracker):
    match = re.match(
        r"(.+) (laganna|í lögunum)(( ,)? ásamt fyrirsögn(um)?,?)? (fellur|falla) brott(, ásamt fyrirsögn)?\.",
        tracker.current_text,
    )
    if match is None:
        return False

    address = match.groups()[0]

    try:
        intent = tracker.make_intent("delete", address)
    except NoSuchLawException:
        # FIXME: This is a temporary measure to deal with lög nr. 140/2024,
        # which removes content from a change-law that isn't a part of the
        # codex. For now, we will force this to error out here, not recognizing
        # the intent"A-liður 11. gr. laganna fellur brott.".
        #
        # This is exceedingly rare and may be dangerous in terms of tracing
        # legislative changes.
        #
        # It is unclear how we will deal with this permanently, but we'll be
        # better equipped to deal with this once we are able to parse changes
        # to bills and change proposals, since this will need to effectively do
        # the same thing.
        return False

    tracker.intents.append(intent)

    return True


def parse_inner_table(tracker: IntentTracker):
    if tracker.lines.current.tag != "table":
        return False

    table = E("table")

    tbody = E("tbody")
    table.append(tbody)

    for in_tr in tracker.lines.current.xpath("tbody/tr"):

        tr = E("tr")
        tbody.append(tr)

        for in_td in in_tr.findall("td"):
            td = E("td")
            tr.append(td)

            in_em = in_td.find("em")
            if in_em is not None:
                # FIXME: Missing support for `table-nr-title`.
                td.attrib["header-style"] = "i"
                td.append(E("table-title", in_em.text))
            else:
                add_sentences(td, separate_sentences(in_td.text))

    tracker.targets.inner.append(table)

    return True


def parse_inner_art_name(tracker: IntentTracker):
    if not (
        "style" in tracker.lines.current.attrib
        and tracker.lines.current.attrib["style"] == "text-align: center;"
    ):
        return False

    em = tracker.lines.current.find("em")
    if em is None:
        return False

    tracker.inner_targets.art.append(E("name", em.text))

    return True


def parse_inner_art_numarts(tracker: IntentTracker):
    # if ol is None:
    #    ol = tracker.lines.current
    ol = tracker.lines.current

    if ol.tag != "ol":
        return False

    # Figure out the number type.
    nr_type = ""
    if (
        "style" in ol.attrib and ol.attrib["style"] == "list-style-type: lower-alpha;"
    ) or ("type" in ol.attrib and ol.attrib["type"] == "a"):
        nr_type = "alphabet"
    else:
        nr_type = "numeric"

    # Determine pre-target and possibly target.
    target = None
    if len(tracker.inner_targets.numarts) > 0:
        target = tracker.inner_targets.numarts[-1].xpath("paragraph")[-1]
    elif tracker.inner_targets.subart is not None:
        target = tracker.inner_targets.subart.xpath("paragraph")[-1]
    elif tracker.targets.inner is not None:
        target = tracker.targets.inner
    else:
        raise IntentParsingException("Can't find pre-target node for numart.")

    # Sometimes the parsed stuff doesn't start at 1, for example when being
    # added to an already existing `numart`.
    seq_start = 1
    if "start" in ol.attrib:
        seq_start = int(ol.attrib["start"])

    lis = ol.findall("li")
    for i, li in enumerate(lis):
        seq = seq_start + i

        # Determine the `nr` that will belong to the `numart`. In the adverts,
        # the content relies on browser rendering of CSS styles to render this
        # to the user, instead of literal text.
        nr = ""
        if nr_type == "alphabet":
            nr = chr(ord("a") - 1 + seq)
        else:
            nr = str(seq)

        # Construct `nr_title`.
        nr_title = "%s." % nr

        # Check if there is a name.
        name = ""
        text = li.text.strip()
        if len(text) == 0 and (em := li.find("em")) is not None:
            name = em.text
            text = em.tail.strip()

        # Construct the `numart`.
        numart = E(
            "numart",
            {"nr": nr, "nr-type": nr_type},
            E("nr-title", nr_title),
        )
        if len(name) > 0:
            numart.append(E("name", name))

        add_sentences(numart, separate_sentences(text))

        sub_ols = li.xpath("ol")
        if len(sub_ols) > 0:
            tracker.inner_targets.numarts.append(numart)
            tracker.set_lines(sub_ols)
            for _ in tracker.lines:
                parse_inner_art_numarts(tracker)
            tracker.unset_lines()
            tracker.inner_targets.numarts.pop()

        target.append(numart)

    # Check if there is a paragraph following the `ol`.
    if ol.tail.strip() != "":
        sentences = separate_sentences(ol.tail.strip())
        add_sentences(target.getparent(), sentences)

    return True


def parse_inner_art_subart(tracker: IntentTracker, prefilled: dict = {}):
    """
    Parses a `subart`.

    There are at least two ways of denoting a `subart` in the original content.
    One is where it's an independent tag, usually a `p`. Another way is by
    following a `br` tag. This function supports both ways, but note that when
    it is given a `br`, it actually parses the tail of the node, not its text.
    """
    if not (
        (
            "style" in tracker.lines.current.attrib
            and tracker.lines.current.attrib["style"] == "text-align: justify;"
        )
        # When parsing by `br` tag, the above styling isn't always present.
        or tracker.lines.current.tag == "br"
    ):
        return False

    if "nr" in prefilled:
        nr = int(prefilled["nr"])
    else:
        # Figure out the number from existing `subart`s within the article.
        nr = len(tracker.inner_targets.art.findall("subart")) + 1

    tracker.inner_targets.subart = E("subart", {"nr": str(nr)})

    # Add content. This is done differently depending on whether the content
    # begins at `br` or is contained within its own structure.
    if tracker.lines.current.tag == "br":
        sens = separate_sentences(remove_garbage(tracker.lines.current.tail))
    else:
        sens = separate_sentences(get_all_text(tracker.lines.current))

    add_sentences(tracker.inner_targets.subart, sens)

    # Check if the `subart` contains `numart`s.
    if tracker.lines.peek() is not None and tracker.lines.peek().tag == "ol":
        next(tracker.lines)
        parse_inner_art_numarts(tracker)

    if tracker.inner_targets.art is not None:
        tracker.inner_targets.art.append(tracker.inner_targets.subart)
    else:
        tracker.targets.inner.append(tracker.inner_targets.subart)

    tracker.inner_targets.subart = None

    return True


# FIXME: This function should be called `parse_inner_art_nr_title`. But before
# renaming it, we should make sure that such a renaming won't cause confusion
# where it's used elsewhere in the code.
def parse_inner_art_address(tracker: IntentTracker, only_check: bool = False):
    # Preliminary test to try and make sure that we're truly dealing with a new
    # article's `nr-title` and not something like a weird `numart`.
    if not (
        tracker.lines.current.tag == "br"
        or (
            # FIXME: May be outdated (from Stjornartidindi.is previous version).
            # Check and remove if never used.
            tracker.lines.current.tag == "p"
            and (
                "style" not in tracker.lines.current.attrib
                or tracker.lines.current.attrib["style"] == "text-align: justify;"
            )
        )
    ):
        return False

    match = re.match(r"([a-z]\. )?\((.+)\)", tracker.current_text)

    if match is None:
        return False

    # We may want to only check for the criteria without actually parsing, in
    # which case we exit immediately.
    if only_check:
        return True

    # Support for `prefilled` variables in calling functions of this function.
    # In short, we don't want to override data that has already been filled in
    # by the calling function for some reason, but we still want to communicate
    # that a `nr-title` was indeed found. We don't need to do anything more
    # than that, though, so we'll return here.
    if len(tracker.inner_targets.art.attrib["nr"]) > 0:
        return True

    nr_title = match.groups()[1]

    nr, roman_nr = analyze_art_name(nr_title)

    # Even though we may have parsed a `nr`, `nr_title` and `roman_nr` at this
    # point, the original content may actually be wrong. In these cases, we'll
    # instead need to figure out the correct values by analyzing the content
    # that has already been parsed. This can be determined by checking if we've
    # already created an article that has the same `nr`.
    #
    # Examples:
    # - 4. gr. laga nr. 73/2014
    #   https://www.stjornartidindi.is/Advert.aspx?RecordID=417b28c4-f82c-46c3-a9a8-09ec25807c30
    #
    existing_arts = tracker.targets.inner.xpath("chapter/art")
    if len(existing_arts) > 0:
        last_art = existing_arts[-1]
        if is_roman(last_art.attrib["nr"]):
            new_nr = roman.fromRoman(last_art.attrib["nr"]) + 1
            roman_nr = str(new_nr)
            nr = roman.toRoman(new_nr)
            nr_title = "%s." % nr
        else:
            # This seems to never actually happen, but it's simple enough, so
            # we've left it in here just in case, although with an exception to
            # make sure that it doesn't do unexpected things.
            raise IntentParsingException("Implemented but untested.")
            # nr = str(int(last_art.attrib["nr"]) + 1)
            # nr_title = "%s. gr." % nr

    tracker.inner_targets.art.attrib["nr"] = nr
    tracker.inner_targets.art.find("nr-title").text = nr_title

    # Add Roman information if available.
    if len(roman_nr) > 0:
        tracker.inner_targets.art.attrib["roman-nr"] = roman_nr
        tracker.inner_targets.art.attrib["number-type"] = "roman"

    return True


def parse_inner_art(tracker: IntentTracker, prefilled: dict = {}):
    # NOTE: This is the only current way we have to test for failure to parse
    # immediately. Otherwise, it will have to be determined by the exception
    # thrown in the `for line...` loop inside.
    #
    # We know for a fact that we should continue if anything has been provided
    # to `prefilled`. That's the equivalent of the calling function insisting.
    if tracker.lines.peek() is None and len(prefilled) == 0:
        return False

    # NOTE: This may actually remain empty and be figured out during parsing of
    # `tracker.lines` later, depending on the nature of the content.
    nr_title = ""
    nr = ""
    roman_nr = ""

    # Respect `prefilled["nr_title"]`.
    if "nr_title" in prefilled:
        nr_title = prefilled["nr_title"]

        # Remember, these may both be empty strings if `nr_title` is still
        # empty at this point.
        nr, roman_nr = analyze_art_name(nr_title)

    # Respect `prefilled["nr"]`.
    if "nr" in prefilled:
        nr = prefilled["nr"]

    # Start making article.
    tracker.inner_targets.art = E("art", {"nr": nr})
    tracker.inner_targets.art.append(E("nr-title", nr_title))

    # Add Roman information if available.
    if len(roman_nr) > 0:
        tracker.inner_targets.art.attrib["roman-nr"] = roman_nr
        tracker.inner_targets.art.attrib["number-type"] = "roman"

    address_is_parsed = False
    for line in tracker.lines:
        # If we run into an article address when we already have one, we should
        # start a new article.
        if address_is_parsed and parse_inner_art_address(tracker, only_check=True):
            # Take back the attempt to parse this thing, so that the calling
            # function can.
            tracker.lines.index -= 1
            break

        # No need to parse `nr-title` if already parsed.
        if parse_inner_art_address(tracker):
            address_is_parsed = True
            continue
        if parse_inner_art_name(tracker):
            continue
        if parse_inner_art_subart(tracker):
            continue

        raise IntentParsingException(
            "Don't know what to do with line: %s" % get_all_text(line)
        )

    if "text_to" in prefilled:
        sentences = separate_sentences(prefilled["text_to"])
        add_sentences(tracker.inner_targets.art, sentences)

    # If the `nr` hasn't been provided at this point, neither through
    # `prefilled` nor by analyzing the parsed content, we need to figure that
    # out based on existing content.
    if tracker.inner_targets.art.attrib["nr"] == "":
        # First, we try going by the content we've added.
        try:
            last_art = tracker.targets.inner.xpath("chapter/art")[-1]
        except IndexError:
            # If no such content exists, we'll try the content that should
            # already have been found earlier.
            try:
                last_art = tracker.intents.xpath(".//intent/existing//art")[-1]
            except IndexError:
                # Alright. We give up.
                raise IntentParsingException("Can't figure new out article number.")

        next_art = construct_node(last_art)
        for attr in ["nr", "roman-nr", "number-type"]:
            tracker.inner_targets.art.attrib[attr] = next_art.attrib[attr]
        tracker.inner_targets.art.find("nr-title").text = next_art.find("nr-title").text

    if tracker.inner_targets.chapter is not None:
        tracker.inner_targets.chapter.append(tracker.inner_targets.art)
    else:
        tracker.targets.inner.append(tracker.inner_targets.art)

    tracker.inner_targets.art = None

    return True


def parse_a_eftir_x_laganna_kemur_malsgrein_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Á eftir (.+) laganna (kemur|koma) (ný málsgrein|(tvær|þrjár|fjórar|fimm) nýjar málsgreinar), svohljóðandi:",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, _ = match.groups()

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "subart":
        nr = int(existing[0].attrib["nr"])
        for _ in tracker.lines:
            nr += 1
            parse_inner_art_subart(tracker, {"nr": nr})
    else:
        raise IntentParsingException(
            "Don't know how to add subart at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_a_undan_x_laganna_kemur_malsgrein_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Á undan (.+) laganna (kemur|koma) (ný málsgrein|(tvær|þrjár|fjórar|fimm) nýjar málsgreinar), svohljóðandi:",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, _ = match.groups()

    intent = tracker.make_intent("prepend", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "subart":
        nr = int(existing[0].attrib["nr"])
        for _ in tracker.lines:
            nr += 1
            parse_inner_art_subart(tracker, {"nr": nr})
    else:
        raise IntentParsingException(
            "Don't know how to add subart at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_vid_x_laganna_baetist_malsgrein_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við (.+) (laganna|í lögunum) bæt[ia]st (ný málsgrein|(tvær|þrjár|fjórar) nýjar málsgreinar), svohljóðandi:",
        tracker.current_text,
    )
    if match is None:
        return False

    address = match.groups()[0]

    intent = tracker.make_intent("add", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "art":

        nr = len(existing[0].findall("subart"))
        for _ in tracker.lines:
            nr += 1
            parse_inner_art_subart(tracker, {"nr": nr})

    else:
        raise IntentParsingException(
            "Don't know how to add subart at address: %s" % address
        )

    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)
    tracker.targets.inner = None

    return True


def parse_sub_intents(tracker: IntentTracker):
    if tracker.lines.current.tag != "ol":
        return False

    tracker.set_lines(tracker.lines.current.findall("li"))

    for li in tracker.lines:

        if parse_a_eftir_ordinu_x_i_x_kemur(tracker):
            pass
        elif parse_a_eftir_ordinu_x_kemur(tracker):
            pass
        elif parse_a_eftir_x_kemur_tolulidur_svohljodandi(tracker):
            pass
        elif parse_a_eftir_x_kemur_malslidur_svohljodandi(tracker):
            pass
        elif parse_a_eftir_x_kemur_malsgrein_svohljodandi(tracker):
            pass
        elif parse_a_undan_ordinu_x_kemur(tracker):
            pass
        elif parse_a_undan_ordinu_x_i_x_kemur(tracker):
            pass
        elif parse_a_undan_x_kemur_nyr_tolulidur(tracker):
            pass
        elif parse_eftirfarandi_breytingar_verda_a_x(tracker):
            pass
        elif parse_fyrirsogn_greinarinnar_verdur(tracker):
            pass
        elif parse_i_stad_ordsins_x_tvivegis_i_x_og_einu_sinni_i_x_kemur(tracker):
            pass
        elif parse_i_stad_x_kemur(tracker):
            pass
        elif parse_i_stad_x_i_x_kemur(tracker):
            pass
        elif parse_i_stad_x_kemur_nyr_malslidur_svohljodandi(tracker):
            pass
        elif parse_i_stad_x_kemur_malslidur_svohljodandi(tracker):
            pass
        elif parse_ordid_x_fellur_brott(tracker):
            pass
        elif parse_ordid_x_i_x_fellur_brott(tracker):
            pass
        elif parse_vid_baetist_malslidur_svohljodandi(tracker):
            pass
        elif parse_vid_baetast_x_nyir_tolulidir_sem_verda_x_svohljodandi(tracker):
            pass
        elif parse_vid_baetist_malsgrein_svohljodandi(tracker):
            pass
        elif parse_vid_baetist_nyr_tolulidur_svohljodandi(tracker):
            pass
        elif parse_vid_baetist_nyr_tolulidur_x_svohljodandi(tracker):
            pass
        elif parse_vid_x_baetist(tracker):
            pass
        elif parse_vid_x_baetist_tolulidur_svohljodandi(tracker):
            pass
        elif parse_vid_x_baetist_malslidur_svohljodandi(tracker):
            pass
        elif parse_x_fellur_brott(tracker):
            pass
        elif parse_x_ordast_svo(tracker):
            pass
        else:
            raise IntentParsingException(
                "Can't figure out list text: %s" % get_all_text(li)
            )

    tracker.unset_lines()

    return True


def parse_eftirfarandi_breytingar_verda_a_x(tracker: IntentTracker):
    match = re.match(
        r"Eftirfarandi breytingar verða á (tollskrárnúmerum í )?(.+?):",
        tracker.current_text,
    )
    if match is None:
        return False

    _, address = match.groups()

    # We are 2 levels deep here. We'll need an extra layer of `intents`.
    # Hopefully this is the only place. If this ends up being required
    # elsewhere, we might  apply a similar strategy to what we do with the
    # `set_lines` and `unset_lines` functions to recurse through nodes.
    #
    # Example:
    #  - A-stafl. 7. gr. laga nr. 68/2024:
    #    https://www.stjornartidindi.is/Advert.aspx?RecordID=559fef86-a7a2-4285-afd3-8f94a271e55f
    lower_intents = E("intents", {"common-address": address})
    upper_intents = tracker.intents
    upper_intents.append(lower_intents)
    tracker.intents = lower_intents

    tracker.set_lines(tracker.lines.current.xpath("ol"))

    for _ in tracker.lines:
        if parse_sub_intents(tracker):
            continue

        raise IntentParsingException(
            "Can't figure out sub-intents at address: %s" % address
        )

    tracker.unset_lines()

    tracker.intents = upper_intents

    return True


def parse_i_stad_ordsins_x_tvivegis_i_x_og_einu_sinni_i_x_kemur(tracker: IntentTracker):
    match = re.match(
        r"Í stað orðins „(.+)“ tvívegis í (.+) og einu sinni í (.+) kemur: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    text_from, address_1, address_2, text_to = match.groups()

    intent_1 = tracker.make_intent("replace_text", address_1)
    intent_1.append(E("text-from", text_from))
    intent_1.append(E("text-to", text_to))

    intent_2 = tracker.make_intent("replace_text", address_2)
    intent_2.append(E("text-from", text_from))
    intent_2.append(E("text-to", text_to))

    tracker.intents.append(intent_1)
    tracker.intents.append(intent_2)

    return True


def parse_a_undan_ordinu_x_kemur(tracker: IntentTracker):
    match = re.match(
        r"Á undan (orðinu|orðunum) „(.+)“ kemur: (.+)", tracker.current_text
    )
    if match is None:
        return False

    address = ""
    _, text_from, text_to = match.groups()

    intent = tracker.make_intent("prepend_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_a_undan_ordinu_x_i_x_kemur(tracker: IntentTracker):
    match = re.match(
        r"Á undan (orðinu|orðunum) „(.+)“ í (.+) kemur: (.+)", tracker.current_text
    )
    if match is None:
        return False

    _, text_from, address, text_to = match.groups()

    intent = tracker.make_intent("prepend_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_a_undan_x_kemur_nyr_tolulidur(tracker: IntentTracker):
    match = re.match(
        r"Á undan (.+) kemur nýr töluliður, svohljóðandi: (.+)", tracker.current_text
    )
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("prepend", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "numart":
        inner.append(construct_node(existing[0], text_to, nr_change=0))
    else:
        raise IntentParsingException(
            "Don't know how to prepend numart at address: %s" % address
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_i_stad_x_kemur(tracker: IntentTracker):
    match = re.match(
        r"([a-z]\. )?Í stað( (orðsins|orðanna|fjárhæðarinnar))? „(.+)“( í (.+?) skiptið)? kemur: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address = ""
    _, _, _, text_from, _, instance_num_raw, text_to = match.groups()

    intent = tracker.make_intent("replace_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    if instance_num_raw is not None:
        if instance_num_raw == "fyrra":
            instance_num = 1
        elif instance_num_raw == "síðara":
            instance_num = 2
        else:
            raise IntentParsingException(
                "Don't know how to translate into instance_num: %s" % instance_num_raw
            )

        intent.attrib["instance-num"] = str(instance_num)

    tracker.intents.append(intent)

    return True


def parse_i_stad_x_kemur_nyr_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Í stað (.+) kemur nýr málsliður, svohljóðandi: (.+)", tracker.current_text
    )
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("replace", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) > 0 and all([n.tag == "sen" for n in existing]):
        for sen in construct_sens(existing[0], text_to):
            inner.append(sen)
    else:
        raise IntentParsingException(
            "Don't know how to replace unsupported tags at address: %s" % address
        )

    intent.append(inner)

    tracker.intents.append(intent)

    return True


def parse_a_eftir_ordinu_x_i_x_kemur(tracker: IntentTracker):
    match = re.match(
        r"Á eftir (orðinu|orðunum|skammstöfuninni) „(.+)“ í (.+) kemur: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    _, text_from, address, text_to = match.groups()

    intent = tracker.make_intent("append_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_a_eftir_ordinu_x_kemur(tracker: IntentTracker):
    match = re.match(
        r"Á eftir (orðinu|orðunum) „(.+)“ kemur: (.+)", tracker.current_text
    )
    if match is None:
        return False

    address = ""
    _, text_from, text_to = match.groups()

    intent = tracker.make_intent("append_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_a_eftir_x_kemur_tolulidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Á eftir (.+) kemur nýr (tölu|staf)liður, svohljóðandi(, og breytist röð annarra (tölu|staf)liða samkvæmt því)?: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, _, text_to = match.groups()

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "numart":
        inner.append(construct_node(existing[0], text_to))
    else:
        raise IntentParsingException(
            "Don't know how to append numart at address: %s" % address
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_a_eftir_x_kemur_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Á eftir (.+) (kemur|koma) (nýr málsliður|(tveir|þrír|fjórir) nýir málsliðir), svohljóðandi: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, _, text_to = match.groups()

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) > 0 and all([n.tag == "sen" for n in existing]):
        for sen in construct_sens(existing[0], text_to, nr_change=1):
            inner.append(sen)
    else:
        raise IntentParsingException(
            "Don't know how to append numart at address: %s" % address
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_a_eftir_x_kemur_malsgrein_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Á eftir (.+) (kemur|koma) (ný málsgrein|(tvær|þrjár|fjórar) nýjar málsgreinar), svohljóðandi: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, _, text_to = match.groups()

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "subart":
        nr = int(existing[0].attrib["nr"])

        tracker.set_lines(list(tracker.lines.current))

        for _ in tracker.lines:
            nr += 1
            if not parse_inner_art_subart(tracker, {"nr": nr}):
                raise IntentParsingException(
                    "Expected subart but got something else at address: %s" % address
                )

        tracker.unset_lines()
    else:
        raise IntentParsingException(
            "Don't know how to append subart at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_vid_x_baetist(tracker: IntentTracker):
    match = re.match(r"Við (.+) bætist: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("add_text", address)
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_ordid_x_fellur_brott(tracker: IntentTracker):
    match = re.match(
        r"(Orðið|Orðin) „(.+)“ (fellur|falla) brott\.", tracker.current_text
    )
    if match is None:
        return False

    address = ""
    _, text_from, _ = match.groups()

    intent = tracker.make_intent("delete_text", address)
    intent.append(E("text-from", text_from))

    tracker.intents.append(intent)

    return True


def parse_x_fellur_brott(tracker: IntentTracker):
    match = re.match(r"(.+) (fellur|falla) brott\.", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]

    tracker.intents.append(tracker.make_intent("delete", address))

    return True


def parse_ordid_x_i_x_fellur_brott(tracker: IntentTracker):

    # FIXME: This should belong to the planned "prologue" parsing mentioned in
    # the function `parse_i_stad_x_i_x_kemur`.
    text = tracker.current_text
    search = re.search(r" og sama orð hvarvetna annars staðar í lögunum", text)
    if search is not None:
        text = text.replace(search.group(), "")

    # --- Start of traditional parsing. ---

    match = re.match(
        r"(Orðið|Orðin|Tilvísunin) „(.+)“( tvívegis)? í (.+?)( laganna| í lögunum)? (fellur|falla) brott\.",
        text,
    )
    if match is None:
        return False

    _, text_from, _, address, _, _ = match.groups()

    intent = tracker.make_intent("delete_text", address)
    intent.append(E("text-from", text_from))

    tracker.intents.append(intent)

    return True


def parse_vid_x_baetist_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við (.+) bæt[ia]st (nýr málsliður|(tveir|þrír|fjórir) nýir málsliðir), svohljóðandi: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, text_to = match.groups()

    intent = tracker.make_intent("add", address, "sen")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["art", "subart", "numart"]:
        nr = len(existing[0].xpath("//paragraph")[-1].findall("sen"))
        sentences = separate_sentences(text_to)
        for sentence in sentences:
            nr += 1
            inner.append(E("sen", {"nr": str(nr)}, sentence))
    else:
        raise IntentParsingException(
            "Don't know how to add sentence at address: %s"
            % tracker.intents.attrib["common-address"]
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_vid_baetist_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við bæt[ia]st (nýr málsliður|(tveir|þrír|fjórir) nýir málsliðir), svohljóðandi: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address = ""
    _, _, text_to = match.groups()

    intent = tracker.make_intent("add", address, "sen")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["art", "subart", "numart"]:
        nr = len(existing[0].xpath("//paragraph")[-1].findall("sen"))
        sentences = separate_sentences(text_to)
        for sentence in sentences:
            nr += 1
            inner.append(E("sen", {"nr": str(nr)}, sentence))
    else:
        raise IntentParsingException(
            "Don't know how to add sentence at address: %s"
            % tracker.intents.attrib["common-address"]
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_vid_baetast_x_nyir_tolulidir_sem_verda_x_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við bætast (tveir|þrír|fjórir) nýir töluliðir, sem verða (.+), svohljóðandi:",
        tracker.current_text,
    )
    if match is None:
        return False

    address_to = match.groups()[1]

    intent = tracker.make_intent("insert", address_to)
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")
    if len(existing) == 2 and all([n.tag == "numart" for n in existing]):
        tracker.set_lines(tracker.lines.current.xpath("ol"))
        for _ in tracker.lines:
            parse_inner_art_numarts(tracker)
        tracker.unset_lines()
    else:
        raise IntentParsingException(
            "Don't know how to add numart at address: %s"
            % tracker.intents.attrib["common-address"]
        )

    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)
    tracker.targets.inner = None

    return True


def parse_vid_baetist_malsgrein_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við bæt(a|i)st (ný málsgrein|(tvær|þrjár) nýjar málsgreinar), svohljóðandi:( .+)?",
        tracker.current_text,
    )
    if match is None:
        return False

    address = ""
    _, _, _, text_to = match.groups()

    intent = tracker.make_intent("add", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "art":

        nr = len(existing[0].findall("subart"))

        if text_to is not None:
            tracker.set_lines(list(tracker.lines.current))
            for _ in tracker.lines:
                nr += 1
                parse_inner_art_subart(tracker, {"nr": nr})
            tracker.unset_lines()

    else:
        raise IntentParsingException(
            "Don't know how to add subart at address: %s" % address
        )

    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)
    tracker.targets.inner = None

    return True


def parse_vid_baetist_nyr_tolulidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við bætist nýr (tölu|staf)liður, svohljóðandi: (.+)", tracker.current_text
    )
    if match is None:
        return False

    address = ""
    _, text_to = match.groups()

    intent = tracker.make_intent("add", address, node_hint="numart")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["art", "subart", "numart"]:
        base_numart = existing[0].xpath("//numart")[-1]
        inner.append(construct_node(base_numart, text_to))
    else:
        raise IntentParsingException(
            "Don't know how to add numart at address: %s" % address
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_vid_x_baetist_tolulidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við (.+) bætist nýr (tölu|staf)liður, svohljóðandi: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, text_to = match.groups()

    intent = tracker.make_intent("add", address, node_hint="numart")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["art", "subart"]:
        base_numart = existing[0].xpath("//numart")[-1]
        inner.append(construct_node(base_numart, text_to))
    else:
        raise IntentParsingException(
            "Don't know how to add numart at address: %s" % address
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_vid_baetist_nyr_tolulidur_x_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við bætist nýr töluliður(,| sem verður) (.+), svohljóðandi: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    _, address_to, text_to = match.groups()

    intent = tracker.make_intent("insert", address_to, node_hint="numart")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "numart":
        inner.append(construct_node(existing[0], text_to, nr_change=0))
    else:
        raise IntentParsingException(
            "Don't know how to add numart at address: %s" % address_to
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_fyrirsogn_greinarinnar_verdur(tracker: IntentTracker):
    match = re.match(
        r"Fyrirsögn greinarinnar (verður|orðast svo): (.+)", tracker.current_text
    )
    if match is None:
        return False

    address = ""
    _, name = match.groups()

    intent = tracker.make_intent("replace", address, "name")

    inner = E("inner", E("name", name))

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_x_ordast_svo(tracker: IntentTracker):
    match = re.match(r"(.+?)( laganna)? orðast svo: ?(.+)?", tracker.current_text)
    if match is None:
        return False

    address, _, text_to = match.groups()

    intent = tracker.make_intent("replace", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)

    if len(existing) == 1 and existing[0].tag == "subart":

        prefilled = {
            "nr": existing[0].attrib["nr"],
        }

        tracker.set_lines(list(tracker.lines.current))
        for _ in tracker.lines:
            parse_inner_art_subart(tracker, prefilled=prefilled)
        tracker.unset_lines()

    elif len(existing) == 1 and existing[0].tag == "numart":
        tracker.targets.inner.append(construct_node(existing[0], text_to, nr_change=0))

    elif len(existing) == 1 and existing[0].tag == "name":
        name = E("name", text_to)
        tracker.targets.inner.append(name)

    elif len(existing) > 0 and all([i.tag == "sen" for i in existing]):
        for sen in construct_sens(existing[0], text_to):
            tracker.targets.inner.append(sen)

    elif len(existing) == 1 and existing[0].tag == "appendix":
        tracker.targets.inner.append(construct_appendix())

    else:
        raise IntentParsingException(
            "Don't know how to replace content at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_tafla_i_x_ordast_svo(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_tafla_i_x_laganna_ordast_svo
    match = re.match(r"([a-z])\. (Tafla í (.+)) orðast svo:", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[1]

    intent = tracker.make_intent("replace", address)

    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)

    next(tracker.lines)

    parse_inner_table(tracker)

    tracker.targets.inner = None

    return True


def parse_tafla_i_x_laganna_ordast_svo(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_tafla_i_x_ordast_svo
    match = re.match(r"(Tafla í (.+)) laganna orðast svo:", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]

    intent = tracker.make_intent("replace", address)

    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)

    next(tracker.lines)

    parse_inner_table(tracker)

    tracker.targets.inner = None

    return True


def parse_vid_gildistoku_laga_thessara_verdur_eftirfarandi_breyting_a_logum_nr_x(
    tracker: IntentTracker,
):
    # TODO: Great candidate for merging with:
    #     parse_vid_gildistoku_laga_thessara_verda_eftirfarandi_breytingar_a_logum_nr_x
    match = re.match(
        r"Við gildistöku laga þessara verður eftirfarandi breyting á lögum( um .+)?, nr\. (\d{1,3}\/\d{4}) ?: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    _, identifier, text = match.groups()

    tracker.set_affected_law_identifier(identifier)

    if parse_i_stad_x_i_x_kemur(tracker, text):
        pass
    elif parse_a_eftir_ordinu_x_i_x_laganna_kemur(tracker, text):
        pass
    elif parse_vid_login_baetist_nytt_x_svohljodandi(tracker, text):
        pass
    else:
        raise IntentParsingException("Don't know how to deal with: %s" % text)

    return True


def parse_vid_gildistoku_laga_thessara_verda_eftirfarandi_breytingar_a_logum_nr_x(
    tracker: IntentTracker,
):
    # TODO: Great candidate for merging with:
    #     parse_vid_gildistoku_laga_thessara_verdur_eftirfarandi_breyting_a_logum_nr_x
    match = re.match(
        r"Við gildistöku laga þessara verða eftirfarandi breytingar á lögum( um .+)?, nr\. (\d{1,3}\/\d{4}) ?:",
        tracker.current_text,
    )
    if match is None:
        return False

    _, identifier = match.groups()

    tracker.set_affected_law_identifier(identifier)

    if tracker.lines.peek().tag == "ol":
        next(tracker.lines)
        tracker.set_lines(tracker.lines.current.xpath("li"))
        for _ in tracker.lines:
            if parse_i_stad_x_i_x_kemur(tracker):
                pass
            elif parse_x_laganna_fellur_brott(tracker):
                pass
            elif parse_vid_login_baetist_nytt_x_svohljodandi(tracker):
                pass
            elif parse_eftirfarandi_breytingar_verda_a_x_laganna(tracker):
                pass
            elif parse_x_laganna_verdur(tracker):
                pass
            else:
                raise IntentParsingException("Can't figure out sub-list item.")

        tracker.unset_lines()
    else:
        raise IntentParsingException("Don't know how to make changes to other law.")

    return True


def parse_vid_gildistoku_laga_thessara_verda_eftirfarandi_breytingar_a_odrum_logum(
    tracker: IntentTracker,
):
    match = re.match(
        r"Við gildistöku laga þessara verða eftirfarandi breytingar á öðrum lögum:",
        tracker.current_text,
    )
    if match is None:
        return False

    if tracker.lines.peek().tag == "ol":
        next(tracker.lines)
        for law_li in tracker.lines.current.findall("li"):

            # Find the identifier of the affected law.
            full_law_identifier = get_all_text(law_li.find("em")).strip(":").strip()
            identifiers = re.search(
                r"nr\. (\d{1,3}\/\d{4})", full_law_identifier
            ).groups()
            if len(identifiers) != 1:
                raise IntentParsingException(
                    "Expected exactly one law identifier but received: %s" % identifiers
                )
            identifier = identifiers[0]
            del full_law_identifier, identifiers

            tracker.set_affected_law_identifier(identifier)

            sub_lis: list = law_li.xpath("ol/li")

            # A bit of a hack here. Sometimes the intent text is described in
            # the tail of an `em` tag instead of being listed in an `ol/li` as
            # shown above. We respond by artificially constructing the same
            # data structure as expected so that the parsing functions below
            # can properly deal with the content. The alternative to this is
            # "fixing" the original files, but that is even more cumbersome and
            # not obviously better in any way.
            #
            # Examples:
            #
            # - 11. gr. laga nr. 40/2024
            #   https://www.stjornartidindi.is/Advert.aspx?RecordID=ab1346fa-54da-4673-8da4-abf659e230a6
            #
            # - 2. tölul. 8. gr. laga nr. 66/2024
            #   https://www.stjornartidindi.is/Advert.aspx?RecordID=bcea380e-be00-4f16-8603-3b72829e27e3
            #
            text = law_li.find("em").tail.strip()
            if len(text) > 0:
                fake_li = E("li", {"style": "text-align: justify;"}, text)

                # A hopefully rare co-occurrence of the intent text being
                # placed in `text`, but there also being an `ol` list. In these
                # cases, we move the `ol` into the `fake_li` so that the
                # parsing functions below will run into it after dealing with
                # the recently faked `li`.
                #
                # Example:
                # - 1. tölul. 21. gr. laga nr. 106/2024:
                #   https://www.stjornartidindi.is/Advert.aspx?RecordID=9b53e14f-eb18-414c-9393-16590143dac4
                if len(sub_lis) > 0:
                    fake_li.append(deepcopy(law_li.xpath("ol")[0]))
                else:
                    # This can also happen. We are only aware of it occurring
                    # with a single `br` but we'll iterate through them all
                    # just in case.
                    for br in law_li.findall("br"):
                        # We `deepcopy` to prevent changes to `br` affecting
                        # the original node.
                        fake_li.append(deepcopy(br))

                sub_lis = [fake_li]

            tracker.set_lines(sub_lis)

            for _ in tracker.lines:
                if parse_a_eftir_x_laganna_kemur_grein_x_svohljodandi(tracker):
                    pass
                elif parse_a_undan_x_laganna_kemur_malsgrein_svohljodandi(tracker):
                    pass
                elif parse_eftirfarandi_breytingar_verda_a_x_laganna(tracker):
                    pass
                elif parse_fyrirsogn_greinarinnar_verdur(tracker):
                    pass
                elif parse_i_stad_x_i_x_kemur(tracker):
                    pass
                elif parse_i_stad_x_i_x_og_x_i_x_kemur(tracker):
                    pass
                elif parse_ordid_x_i_x_fellur_brott(tracker):
                    pass
                elif parse_vid_login_baetist_nytt_x_svohljodandi(tracker):
                    pass
                elif parse_vid_x_laganna_baetist_malslidur_svohljodandi(tracker):
                    pass
                elif parse_vid_x_laganna_baetist_malsgrein_svohljodandi(tracker):
                    pass
                elif parse_x_laganna_fellur_brott(tracker):
                    pass
                elif parse_x_ordast_svo(tracker):
                    pass
                else:
                    raise IntentParsingException(
                        "Can't figure out sub-list text: %s" % tracker.current_text
                    )

            tracker.unset_lines()
    else:
        raise IntentParsingException(
            "Don't know how to handle tag when changing other laws at enactment: %s"
            % tracker.lines.peek().tag
        )

    return True


def parse_appendix_change(tracker: IntentTracker):
    match = re.match(r"(.+) (viðauka (.+)) við lögin", tracker.current_text)
    if match is None:
        return False

    _, _, raw_nr = match.groups()

    intent = tracker.make_appendix_intent(raw_nr)

    tracker.intents.append(intent)

    return True


def parse_eftirfarandi_breytingar_verda_a_x_laganna(tracker: IntentTracker):
    # TODO: Consider merging with:
    #     parse_eftirfarandi_breytingar_verda_a_x
    # NOTE: That questionable space at the end happens occurs in advert 45/2024.
    match = re.match(
        r"Eftirfarandi breytingar verða á (.+) (laganna|í lögunum) ?:",
        tracker.current_text,
    )
    if match is None:
        return False

    address = match.groups()[0]

    # Because we need to iterate by different means, depending on the nature of
    # the content, we need to check the next item, rather than the current one,
    # to determine how to iterate.
    if tracker.lines.peek() is not None and tracker.lines.peek().tag == "ol":
        tracker.intents.attrib["common-address"] = address
        next(tracker.lines)
        if parse_sub_intents(tracker):
            pass
        else:
            raise IntentParsingException("Expected to parse a sub-intent but failed.")

    elif tracker.lines.peek() is not None and tracker.lines.peek().tag == "p":
        tracker.intents.attrib["common-address"] = address
        for _ in tracker.lines:
            if parse_tafla_i_x_ordast_svo(tracker):
                continue
            elif parse_i_stad_x_kemur(tracker):
                # Normally these get parsed by `parse_sub_intents` above, but
                # on occasion, the original document presents this information
                # in a `p` tag instead of an `ol` list.
                # Example:
                # - 4. gr. laga nr. 86/2024
                #   https://www.stjornartidindi.is/Advert.aspx?RecordID=ca15fe46-c385-40b5-9499-5aad121271c3
                continue

            raise IntentParsingException(
                "Don't know how to parse p-element: %s"
                % get_all_text(tracker.lines.peek())
            )

    elif (ols := tracker.lines.current.xpath("ol")) is not None:
        lower_intents = E("intents", {"common-address": address})
        upper_intents = tracker.intents
        upper_intents.append(lower_intents)
        tracker.intents = lower_intents

        tracker.set_lines(ols)
        next(tracker.lines)

        if parse_sub_intents(tracker):
            pass
        else:
            raise IntentParsingException("Expected to parse a sub-intent but failed.")

        tracker.unset_lines()

        tracker.intents = upper_intents

    else:
        raise IntentParsingException(
            "Unexpected tag for sub-change: %s" % tracker.lines.peek().tag
        )

    return True


def parse_vid_gildistoku_laga_thessara_verda_eftirfarandi_breytingar_a_x_i_logum_um_x_nr_x(
    tracker: IntentTracker,
):
    match = re.match(
        r"Við gildistöku laga þessara verða eftirfarandi breytingar á (.+) í lögum um (.+), nr. (\d{1,3}\/\d{4}) ?:",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, identifier = match.groups()

    tracker.set_affected_law_identifier(identifier)
    tracker.intents.attrib["common-address"] = address

    if tracker.lines.peek().tag == "ol":
        next(tracker.lines)
        if parse_sub_intents(tracker):
            pass
        else:
            raise IntentParsingException("Expected to parse a sub-intent but failed.")

    else:
        raise IntentParsingException(
            "Unexpected tag for sub-change: %s" % tracker.lines.peek().tag
        )

    return True


def parse_x_nr_x_falla_ur_gildi(tracker: IntentTracker):
    match = re.match(
        r"(.+), nr. (\d{1,3}\/\d{4}) ?, falla úr gildi.", tracker.current_text
    )
    if match is None:
        return False

    _, identifier = match.groups()

    intent = tracker.make_repeal(identifier)

    tracker.intents.append(intent)

    return True


def parse_eftirfarandi_log_eru_felld_ur_gildi(tracker: IntentTracker):
    match = re.match(r"Eftirtalin lög eru felld úr gildi:", tracker.current_text)
    if match is None:
        return False

    next(tracker.lines)

    if tracker.lines.current.tag != "ol":
        raise IntentParsingException(
            "Expected 'ol' tag but received: %s" % tracker.lines.current.tag
        )

    law_permutations = get_law_name_permutations(tracker.get_codex_version())

    for li in tracker.lines.current.xpath("li"):
        # NOTE: More than one law can be repealed in a single line.
        # Example:
        # - 1. tölul. 1. gr. laga nr. 50/2024:
        #   https://www.stjornartidindi.is/Advert.aspx?RecordID=8b1987cc-f52c-4315-9d46-db1d66f81578

        texts = get_all_text(li).strip(".")
        for text in texts.split(", og "):

            match = re.match(r"(.+), nr\. (\d{1,3}\/\d{4})", text)
            name, identifier = match.groups()

            if identifier not in law_permutations:
                raise IntentParsingException(
                    "Tried repealing non-existent law nr. %s" % identifier
                )

            if (
                name.lower()
                != law_permutations[identifier]["main"]["accusative"].lower()
            ):
                raise IntentParsingException(
                    "Name of repealed law doesn't match: %s" % name
                )

            intent = tracker.make_repeal(identifier)
            tracker.intents.append(intent)

    return True


def parse_a_b___(tracker: IntentTracker):
    # When multiple changes are made in a single article, the article usually
    # starts with something like "Eftirfarandi breytingar verða á...".
    #
    # Example:
    # - 1. gr. laga nr. 44/2024
    #   https://www.stjornartidindi.is/Advert.aspx?RecordID=ca3c8622-2e53-4bd4-bed0-bdffd093458a
    #
    # Sometimes, however, an article just goes straight into describing the
    # changes. Under these circumstances, there is no text to parse, only the
    # list items at the immediate beginning of the article.
    #
    # Example:
    # - 1. gr. laga nr. 66/2024
    #   https://www.stjornartidindi.is/Advert.aspx?RecordID=bcea380e-be00-4f16-8603-3b72829e27e3
    #
    # The latter presumably happens when a change isn't specific to a
    # particular place in the law, but rather is made all over the place.
    #
    # In these circumstances, however, there is nothing to parse at this point,
    # but rather all the checks are made in `parse_sub_intents` already, so we
    # simply return its value. We still want to retain this function here
    # instead of calling `parse_sub_intents` directly from the loop, for
    # consistency's sake. This may very well be revised once we get into
    # merging functions.
    return parse_sub_intents(tracker)


def parse_vid_x_laganna_baetist_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við (.+) laganna bæt[ia]st (nýr málsliður|(tveir|þrír|fjórir) nýir málsliðir), svohljóðandi: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, text_to = match.groups()

    intent = tracker.make_intent("add", address, "sen")
    existing = deepcopy(
        list(intent.find("existing"))
    )  # Only doing `deepcopy` for consistency, it's unnecessary.

    inner = E("inner")
    if len(existing) > 0 and all(
        [(e.tag in ["art", "subart", "numart"]) for e in existing]
    ):
        nr = len(existing[0].xpath("//paragraph")[-1])
        sentences = separate_sentences(text_to)
        for sentence in sentences:
            nr += 1
            inner.append(E("sen", {"nr": str(nr)}, sentence))
    else:
        raise IntentParsingException(
            "Don't know how to add sentence at address: %s" % address
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_a_undan_x_laganna_kemur_ny_grein_x_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Á undan (.+) laganna kemur ný grein, (.+), svohljóðandi:",
        tracker.current_text,
    )
    if match is None:
        return False

    address, nr_title = match.groups()

    intent = tracker.make_intent("prepend", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "art":
        parse_inner_art(tracker, {"nr_title": nr_title})
    else:
        raise IntentParsingException(
            "Don't know how to prepend article at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_x_laganna_faer_fyrirsogn_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"(.+) laganna fær fyrirsögn, svohljóðandi: (.+)", tracker.current_text
    )
    if match is None:
        return False

    address, name = match.groups()

    intent = tracker.make_intent("add", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "art":
        inner.append(E("name", name))
    else:
        raise IntentParsingException(
            "Don't know how to add name at address: %s" % address
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_a_eftir_ordinu_x_i_x_laganna_kemur(tracker: IntentTracker, text: str = ""):
    match = re.match(
        r"Á eftir (orðinu|orðunum|orðhlutanum|tilvísuninni) „(.+)“ í (.+) laganna kemur: (.+)",
        text or tracker.current_text,
    )
    if match is None:
        return False

    _, text_from, address, text_to = match.groups()

    intent = tracker.make_intent("append_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_a_eftir_x_laganna_kemur_nyr_kafli_x_x_x_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Á eftir (.+) laganna kemur nýr kafli, (.+?), (.+), með sjö nýjum greinum, (.+), svohljóðandi(, og breytist kaflanúmer (.+) laganna samkvæmt því)?:",
        tracker.current_text,
    )
    if match is None:
        return False

    address, nr_title, name, _, _, _ = match.groups()

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "art":
        # NOTE: The nomenclature here is the opposite of what it should be.
        # `nr` should be `roman_nr` and `roman_nr` should be `nr`, but at the
        # time of this writing (2025-06-06) this hasn't been updated in the XML
        # yet. We stick to the current and wrong nomenclature to avoid even
        # more confusion, but these should be reversed once the XML is correct.
        roman_nr = analyze_chapter_nr_title(nr_title)
        nr = str(roman.fromRoman(roman_nr))

        tracker.inner_targets.chapter = E(
            "chapter",
            {
                "nr": nr,
                "nr-type": "roman",
                "chapter-type": "kafli",
                "roman-nr": roman_nr,
            },
            E("nr-title", nr_title),
            E("name", name),
        )

        for _ in tracker.lines:
            parse_inner_art(tracker)

        tracker.targets.inner.append(tracker.inner_targets.chapter)
        tracker.inner_targets.chapter = None

    tracker.targets.inner = None

    return True


def parse_a_eftir_x_laganna_kemur_nyr_tolulidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Á eftir (.+) laganna kemur nýr töluliður, svohljóðandi: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    intent.append(inner)
    tracker.intents.append(intent)

    if existing[0].tag == "numart":
        name = ""
        if (em := tracker.lines.current.find("em")) is not None:
            name = em.text
            text_to = em.tail.strip()

        tracker.inner_targets.numarts.append(construct_node(existing[0], text_to, name))

        next(tracker.lines)

        # This will either happen once or not at all, judging from "nýr töluliður"
        # being in the singular above.
        # Occurs in:
        # - 1. gr. laga nr. 48/2024
        parse_inner_art_numarts(tracker)

        inner.append(tracker.inner_targets.numarts[-1])

        tracker.inner_targets.numarts.pop()

    else:
        raise IntentParsingException(
            "Don't know how to add numart at address: %s" % address
        )

    return True


def parse_vid_x_laganna_baetist(tracker: IntentTracker):
    match = re.match(r"Við (.+) (laganna|í lögunum) bætist: (.+)", tracker.current_text)
    if match is None:
        return False

    address, _, text_to = match.groups()

    intent = tracker.make_intent("add_text", address)
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_vid_toflu_i_x_laganna_baetist(tracker: IntentTracker):
    match = re.match(r"Við (töflu í (.+)) laganna bætist:", tracker.current_text)
    if match is None:
        return False

    address, _ = match.groups()

    intent = tracker.make_intent("add", address, "table")
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "table":
        next(tracker.lines)
        if parse_inner_table(tracker):
            pass
        else:
            raise IntentParsingException(
                "Don't know how to parse table content at address: %s" % address
            )
    else:
        raise IntentParsingException(
            "Don't know how to add to table at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_i_stad_x_kemur_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Í stað (.+?)( laganna)? (kemur|koma) ((einn )?nýr málsliður|(tveir|þrír|fjórir) nýir málsliðir)(, svohljóðandi| er orðast svo): (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, _, _, _, _, text_to = match.groups()

    intent = tracker.make_intent("replace", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")
    if len(existing) > 0 and all([n.tag == "sen" for n in existing]):
        for sen in construct_sens(existing[0], text_to, nr_change=0):
            tracker.targets.inner.append(sen)

    else:
        raise IntentParsingException(
            "Don't know how to replace unsupported tags at address: %s" % address
        )

    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)
    tracker.targets.inner = None

    return True


def parse_i_stad_x_laganna_kemur_malsgrein_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Í stað (.+) laganna (kemur|koma) (ný málsgrein|(tvær|þrjár|fjórar) nýjar málsgreinar), svohljóðandi:",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, _ = match.groups()

    intent = tracker.make_intent("replace", address, "subart")
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "subart":
        nr = int(existing[0].attrib["nr"])

        for _ in tracker.lines:
            parse_inner_art_subart(tracker, {"nr": nr})
            nr += 1
    else:
        raise IntentParsingException(
            "Don't know how to add subart at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_i_stad_ordanna_x_og_x_i_x_x_thrivegis_i_x_og_tvivegis_i_x_i_logunum_kemur_i_videigandi_beygingarmynd(
    tracker: IntentTracker,
):
    # FIXME: This function currently only communicates to the XML that some
    # special grammar magic is required to accurately create the new content.
    # This magic should take place here instead of in the applying mechanism.
    match = re.match(
        r"Í stað orðanna „(.+)“ og „(.+)“ í (.+), (.+), þrívegis í (.+) og tvívegis í (.+) í lögunum kemur, í viðeigandi beygingarmynd: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    text_from_1, text_from_2, address_1, address_2, address_3, address_4, text_to = (
        match.groups()
    )

    addresses = [address_1, address_2, address_3, address_4]
    for address in addresses:
        intent = tracker.make_intent("replace_text", address)
        # We will add two instances of `text-from` and rely on the applying
        # mechanism for replacing them both.
        intent.append(E("text-from", text_from_1))
        intent.append(E("text-from", text_from_2))
        intent.append(E("text-to", {"detect-grammar": "case"}, text_to))

        tracker.intents.append(intent)

    return True


def parse_i_stad_x_i_x_kemur(tracker: IntentTracker, text: str = ""):
    # FIXME: The first chunk of code here, parsing flags from the text, can be
    # thought of as the proto-stage of a new parser dedicated to analyzing the
    # text instead of these one-liner regexes in every parsing function.
    #
    # The long-term idea is that we will get rid of these one-liner regexes and
    # the fetching of information from them through groups, instead receiving a
    # dictionary, or possibly an object, that describes the nature of the
    # intent. This object would then be sent to `make_intent`.
    #
    # The terminology here might get convoluted unless we clean it up. An
    # `intent` currently refers to the entire change, including content such as
    # new articles or even new entire chapters. What we need to parse here are
    # kind of prologues to the intent, which merely describe whether something
    # is being added, replaced or what not.
    #
    # NOTE: This mess began as a result of how things are phrased in general
    # terms rather than with precise addresses in:
    #
    # - 8. gr. laga nr. 110/2024
    #   https://www.stjornartidindi.is/Advert.aspx?RecordID=47f65e46-e071-48f5-8300-f622a0f73db1

    text = text or tracker.current_text

    flag_from_elsewhere_in_law = False
    # FIXME: We currently have no process for dealing with "I. viðauka laganna"
    # here, so it's hard-coded for now, hoping that this is unique.
    search = re.search(
        r" og (sama orðs|sömu orða) hvarvetna( í öllum beygingarföllum)? annars staðar í lögunum( og í I. viðauka laganna)?,?",
        text,
    )
    if search is not None:
        # NOTE: If we were in charge of the process, then this wouldn't be
        # allowed in legal text. Addresses of changes should be specified
        # exactly. This occurs in 8. gr. laga nr. 110/2024.
        text = text.replace(search.group(), "")
        flag_from_elsewhere_in_law = True

    search = re.search(r" þ.m.t. í fyrirsögnum greina( og viðaukum laganna)?,?", text)
    if search is not None:
        text = text.replace(search.group(), "")

    search = re.search(r" þ.m.t. í millifyrirsögn á undan (.+?) laganna,", text)
    if search is not None:
        text = text.replace(search.group(), "")

    # -- Start of traditional parsing --

    match = re.match(
        r"Í stað( (orðsins|orðanna|ártalsins|fjárhæðarinnar|heitisins|tilvísunarinnar|dagsetningarinnar|tölunnar))? „(.+)“( tvívegis| fjórum sinnum)? í (.+?)( (laganna|í lögunum))?( að undanskildu(m)? (.+),)? kemur(, í viðeigandi beygingarfalli)?: (.+)",
        text,
    )
    if match is None:
        return False

    _, _, text_from, _, address, _, _, _, _, exclude_address, _, text_to = (
        match.groups()
    )

    intent = tracker.make_intent("replace_text", address)

    e_text_from = E("text-from", text_from)
    if flag_from_elsewhere_in_law:
        e_text_from.attrib["from-elsewhere-in-law"] = "true"
    if exclude_address is not None:
        e_text_from.attrib["exclude-address"] = exclude_address
    intent.append(e_text_from)

    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_i_stad_x_i_x_og_x_i_x_kemur(tracker: IntentTracker):
    match = re.match(
        r"Í stað orðsins „(.+)“ í (.+) og „(.+)“ í (.+) kemur: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    text_from_1, address_1, text_from_2, address_2, text_to = match.groups()

    intent_1 = tracker.make_intent("replace_text", address_1)
    intent_1.append(E("text-from", text_from_1))
    intent_1.append(E("text-to", text_to))

    intent_2 = tracker.make_intent("replace_text", address_2)
    intent_2.append(E("text-from", text_from_2))
    intent_2.append(E("text-to", text_to))

    tracker.intents.append(intent_1)
    tracker.intents.append(intent_2)

    return True


def parse_i_stad_hlutfallstolunnar_x_og_artalsins_x_tvivegis_i_x_i_logunum_kemur(
    tracker: IntentTracker,
):
    match = re.match(
        r"Í stað hlutfallstölunnar „(.+)“ og ártalsins „(.+)“ tvívegis í (.+) í lögunum kemur: (.+); og: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    text_from_1, text_from_2, address, text_to_1, text_to_2 = match.groups()

    intent_1 = tracker.make_intent("replace_text", address)
    intent_1.append(E("text-from", text_from_1))
    intent_1.append(E("text-to", text_to_1))

    intent_2 = tracker.make_intent("replace_text", address)
    intent_2.append(E("text-from", text_from_2))
    intent_2.append(E("text-to", text_to_2))

    tracker.intents.append(intent_1)
    tracker.intents.append(intent_2)

    return True


def parse_a_eftir_x_laganna_kemur_grein_x_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Á eftir (.+) laganna (kemur|koma) (ný grein|(tvær|þrjár|fjórar) nýjar greinar), (.+?)?(, ásamt fyrirsögn(um)?)?, svohljóðandi(, og breytist (greinatala|röð annarra greina) samkvæmt því)?:",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, amount, _, nr_title, _, _, _, _ = match.groups()

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "art":

        if amount == "ný grein":
            # When only one article is added, the `nr_title` is only given in
            # the prologue, not in the parsed content.

            # FIXME: This may break when parsing gets more complicated.
            # A bit of a hack to deal with rare occurrences of an article being
            # added without its new `nr_title` being specified. In these cases,
            # the string following the assumed `nr_title` in the matching regex
            # above will be caught instead of a legit `nr_title`.
            # Examples:
            # - 63/2024
            # - 91/2024
            if nr_title == "ásamt fyrirsögn":
                nr = str(int(existing[0].attrib["nr"]) + 1)
                nr_title = "%s. gr." % nr

            parse_inner_art(tracker, {"nr_title": nr_title})

        else:
            # Not `nr_title` needed from prologue because it will be inside the
            # parsed content.
            while parse_inner_art(tracker):
                pass
    else:
        raise IntentParsingException(
            "Don't know how to append article at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_vid_x_laganna_baetist_grein_x_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við (.+) laganna bæt[ia]st (ný grein|(tvær|þrjár|fjórar) nýjar greinar), (.+?)?(, ásamt fyrirsögn(um)?)?, svohljóðandi(, og breytist (greinatala|röð annarra greina) samkvæmt því)?:",
        tracker.current_text,
    )
    if match is None:
        return False

    address, amount, _, nr_title, _, _, _, _ = match.groups()

    intent = tracker.make_intent("add", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "chapter":

        # FIXME: This is broken.
        # This seems to tentatively work for 140/2024.
        # However, it's changing a change-law, 102/2023, which
        # isn't in the codex.
        #
        # If we download all of the adverts, we can determine
        # whether this is the case, but Stjornartidindi.is has
        # changed its website, so we'll need to upgrade the
        # code to use that, before we can fetch 102/2023.

        if amount == "ný grein":
            # When only one article is added, the `nr_title` is only given in
            # the prologue, not in the parsed content.

            # FIXME: This may break when parsing gets more complicated.
            # A bit of a hack to deal with rare occurrences of an article being
            # added without its new `nr_title` being specified. In these cases,
            # the string following the assumed `nr_title` in the matching regex
            # above will be caught instead of a legit `nr_title`.
            # Examples:
            # - 63/2024
            # - 91/2024
            if nr_title == "ásamt fyrirsögn":
                nr = str(int(existing[0].attrib["nr"]) + 1)
                nr_title = "%s. gr." % nr

            parse_inner_art(tracker, {"nr_title": nr_title})

        else:
            # Not `nr_title` needed from prologue because it will be inside the
            # parsed content.
            while parse_inner_art(tracker):
                pass
    else:
        raise IntentParsingException(
            "Don't know how to append article at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_i_stad_x_laganna_koma_fimm_nyjar_greinar_x_svohljodandi_asamt_fyrirsognum(
    tracker: IntentTracker,
):
    # NOTE: Usually, the phrasing is "ásamt fyrirsögnum, svohljóðandi:" when
    # both of those parts appear, but at least once, it's in the wrong order,
    # so "svohljóðandi, ásamt fyrirsögnum:". We'll just support both. Also,
    # these are not relevant to our processing.
    #
    # Example:
    # - 23. gr. laga nr. 104/2024
    #   https://www.stjornartidindi.is/Advert.aspx?RecordID=e4ce4293-b930-46c6-b055-7a19608707fa
    #
    match = re.match(
        r"Í stað (.+) laganna koma fimm nýjar greinar, (.+)(, ásamt fyrirsögnum)?, svohljóðandi(, ásamt fyrirsögnum)?:",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, _ = match.groups()

    intent = tracker.make_intent("replace", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "art":
        while parse_inner_art(tracker):
            pass
    else:
        raise IntentParsingException(
            "Don't know how to replace art at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_vid_login_baetist_ny_grein_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Við lögin bætist ný grein, svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    # Find the last article that isn't a temporary article, and not in a
    # chapter of temporary clauses.
    law = tracker.affected_law()
    last_art = law.xml().xpath("//art[not(@nr='t') and not(../@nr='t')]")[-1]

    # NOTE: The `strip()` is needed due to a bug in `generate_legal_reference`.
    address = generate_legal_reference(last_art, skip_law=True).strip()

    # The dictation contains no information about what the `nr` of the new
    # article should be, so we'll need to deduce it.
    #
    # Currently, we assume that the last article's `nr` is an integer, but
    # strictly speaking it doesn't have to be. Instead of the `nr-title`
    # "164. gr.", it could be "164. gr. a", which would make the `nr` "164a".
    #
    # However, this is very unlikely to ever occur, because it would require
    # such an article to be added between existing articles, and then all the
    # articles after it being removed. This is currently not known to happen
    # anywhere. In other words, the last article `nr` is likely to always be an
    # integer, so we'll assume that to be the case until we find out otherwise.
    nr_title = "%d. gr." % (int(last_art.attrib["nr"]) + 1)

    intent = tracker.make_intent("append", address)

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    parse_inner_art(tracker, {"nr_title": nr_title})

    tracker.targets.inner = None

    return True


def parse_vid_login_baetist_ny_grein_x_svohljodandi(tracker: IntentTracker):

    # WARNING!
    #
    # This phrasing of the content indicates a slight mistake in the bill,
    # which is easy for a human to mitigate but not obvious to a computer.
    #
    # It designates a new article with a specific nr-title, without explaining
    # **where** to place this new article.
    #
    # This is unusual because if it's being added to the end of the law,
    # there's no need for specifying the new article's nr-title. The fact that
    # the nr-title is explicitly mentioned indicates that it's being added
    # somewhere in between existing articles.
    #
    # In short, an article is being added to some place inside the law, without
    # specifying exactly where. It is left up to the human reader to figure out
    # where, judging by the nr-title of the new article.
    #
    # This is known to occur in the following places:
    #
    # - 3. gr. laga nr. 44/2024
    #   https://www.althingi.is/altext/154/s/1615.html
    #   https://www.stjornartidindi.is/Advert.aspx?RecordID=ca3c8622-2e53-4bd4-bed0-bdffd093458a

    match = re.match(
        r"Við lögin bætist ný grein, (.+), svohljóðandi:", tracker.current_text
    )
    if match is None:
        return False

    nr_title = match.groups()[0]
    del match

    # We need to deduce where to place the new article.
    # It's tempting to write some fancy function to do it, but these cases are
    # hopefully exceedingly rare, so we'll do this now in such a messy way that
    # it borders on hard-coding. If these are more common than we expect, this
    # will need improvement, but our current expectations are such that we
    # can't justify spending much time on making this good enough, if it turns
    # out that these are maybe 2-3 cases altogether. Time will tell.
    # Supported:
    #     11. gr. a
    match = re.match(r"(.+) a$", nr_title)
    if match is None:
        raise IntentParsingException("Can't figure out where to place new article.")

    address = match.groups()[0]

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.intents.append(intent)
    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if existing[0].tag == "art":
        parse_inner_art(tracker, {"nr_title": nr_title})
    else:
        raise IntentParsingException(
            "Don't know how to append article at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_vid_login_baetast_tvo_ny_x_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_vid_login_baetist_nytt_x_svohljodandi
    match = re.match(
        r"Við lögin bætast tvö ný (.+), svohljóðandi:", tracker.current_text
    )
    if match is None:
        return False

    address = match.groups()[0]
    intent = tracker.make_intent("add", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)

    if len(existing) == 0:
        tracker.inner_targets.chapter = E(
            "chapter", {"nr": "t", "nr-type": "temporary-clauses"}
        )
        tracker.targets.inner.append(tracker.inner_targets.chapter)

        parse_inner_art(tracker)
        parse_inner_art(tracker)

        tracker.inner_targets.chapter = None
    elif (
        len(existing) == 1
        and existing[0].tag == "chapter"
        and existing[0].attrib["nr-type"] == "temporary-clauses"
    ):
        art_nr = int(existing[0].xpath("art")[-1].attrib["roman-nr"])
        parse_inner_art(
            tracker, prefilled={"nr_title": "%s." % roman.toRoman(art_nr + 1)}
        )
        parse_inner_art(
            tracker, prefilled={"nr_title": "%s." % roman.toRoman(art_nr + 2)}
        )
    elif (
        len(existing) == 1
        and existing[0].tag == "art"
        and existing[0].attrib["nr"] == "t"
    ):

        # It is highly unusual to change the `action` of an intent at this
        # point, but we allow it in this case, because we need to change an
        # `art` into a `chapter` in this very specific circumstance.
        intent.attrib["action"] = "replace"
        tracker.inner_targets.chapter = construct_temp_chapter_from_art(existing[0])

        tracker.targets.inner.append(tracker.inner_targets.chapter)

        while parse_inner_art(tracker):
            pass

        tracker.inner_targets.chapter = None
    else:
        raise IntentParsingException(
            "Don't know how to add temporary clauses at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_vid_login_baetist_nytt_x_svohljodandi(tracker: IntentTracker, text: str = ""):
    # TODO: Great candidate for merging with:
    #     parse_vid_login_baetast_tvo_ny_x_svohljodandi
    match = re.match(
        r"Við lögin bætist nýtt (.+), svohljóðandi: ?(.+)?",
        text or tracker.current_text,
    )
    if match is None:
        return False

    address, text_to = match.groups()
    intent = tracker.make_intent("add", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)

    prefilled = {}

    if text_to is not None:
        prefilled["text_to"] = text_to

    if len(existing) == 0:
        prefilled["nr_title"] = "I."
        parse_inner_art(tracker, prefilled=prefilled)
    elif (
        len(existing) == 1
        and existing[0].tag == "chapter"
        and existing[0].attrib["nr-type"] == "temporary-clauses"
    ):
        parse_inner_art(tracker, prefilled=prefilled)
    elif (
        len(existing) == 1
        and existing[0].tag == "art"
        and existing[0].attrib["nr"] == "t"
    ):

        # It is highly unusual to change the `action` of an intent at this
        # point, but we allow it in this case, because we need to change an
        # `art` into a `chapter` in this very specific circumstance.
        intent.attrib["action"] = "replace"
        tracker.inner_targets.chapter = construct_temp_chapter_from_art(existing[0])

        tracker.targets.inner.append(tracker.inner_targets.chapter)

        while parse_inner_art(tracker):
            pass

        tracker.inner_targets.chapter = None
    else:
        raise IntentParsingException(
            "Don't know how to add temporary clause at address: %s" % address
        )

    tracker.targets.inner = None

    return True


def parse_ordin_x_i_x_laganna_falla_brott(tracker: IntentTracker):
    match = re.match(r"Orðin „(.+)“ í (.+) laganna falla brott.", tracker.current_text)
    if match is None:
        return False

    text_from, address = match.groups()

    intent = tracker.make_intent("delete_text", address)
    intent.append(E("text-from", text_from))

    tracker.intents.append(intent)

    return True


def parse_a_eftir_x_laganna_kemur_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Á eftir (.+) laganna (kemur|koma) (nýr málsliður|(tveir|þrír|fjórir) nýir málsliðir), svohljóðandi: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, _, text_to = match.groups()

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    if len(existing) == 1 and existing[0].tag == "sen":
        for sen in construct_sens(existing[0], text_to, nr_change=1):
            tracker.targets.inner.append(sen)

    else:
        raise IntentParsingException(
            "Don't know how to add sentence to tag: %s" % existing.tag
        )

    tracker.intents.append(intent)
    tracker.targets.inner = None

    return True


def parse_vid_x_laganna_baetist_tolulidur_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við (.+) (laganna|í lögunum) bæt[ia]st (nýr (tölu|staf)liður|(tveir|þrír|fjórir|fimm|sex|sjö) nýir (tölu|staf)liðir), svohljóðandi: ?(.+)?",
        tracker.current_text,
    )
    if match is None:
        return False

    address, _, _, _, _, _, text_to = match.groups()

    intent = tracker.make_intent("add", address, "numart")
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")

    if (
        len(existing) == 1
        and existing[0].tag in ["subart", "numart", "art"]
        and text_to is not None
    ):
        base_numart = existing[0].xpath("//numart")[-1]
        numart = construct_node(base_numart, text_to)
        tracker.targets.inner.append(numart)

    elif len(existing) == 1 and existing[0].tag == "art" and text_to is None:
        next(tracker.lines)
        parse_inner_art_numarts(tracker)

    else:
        raise IntentParsingException(
            "Don't know how to add numart (numeric) at address: %s" % address
        )

    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)
    tracker.targets.inner = None

    return True


def parse_vid_x_laganna_baetist_nyr_tolulidur_x_svohljodandi(tracker: IntentTracker):
    match = re.match(
        r"Við (.+) laganna bætist nýr töluliður, (.+), svohljóðandi: (.+)",
        tracker.current_text,
    )
    if match is None:
        return False

    address, address_to, text_to = match.groups()
    address = "%s %s" % (address_to, address)

    intent = tracker.make_intent("insert", address, "numart")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "numart":
        inner.append(construct_node(existing[0], text_to, nr_change=0))
    else:
        raise IntentParsingException(
            "Don't know how to add numart at address: %s" % address_to
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_rikisborgararett_skulu_odlast(tracker: IntentTracker):
    match = re.match(r"Ríkisborgararétt skulu öðlast:", tracker.current_text)
    if match is None:
        return False

    next(tracker.lines)

    if tracker.lines.current.tag != "ol":
        raise IntentParsingException(
            "Expected 'ol' tag but received: %s" % tracker.lines.current.tag
        )

    for li in tracker.lines.current.xpath("li"):
        name, born_year, born_country = re.match(
            r"(.+), f\. (\d{4}) [áí] (.+)\.", li.text
        ).groups()

        intent = tracker.make_citizenship(name, born_year, born_country)

        tracker.intents.append(intent)

    return True


def parse_title_breyting_a_odrum_logum(tracker: IntentTracker):
    match = re.match(r"Breyting á öðrum lögum\.", tracker.current_text)
    if match is None:
        return False

    next(tracker.lines)

    if parse_vid_gildistoku_laga_thessara_verdur_eftirfarandi_breyting_a_logum_nr_x(
        tracker
    ):
        pass
    elif parse_vid_gildistoku_laga_thessara_verda_eftirfarandi_breytingar_a_odrum_logum(
        tracker
    ):
        pass
    else:
        raise IntentParsingException(
            "Don't know how to parse changes to other laws: %s" % tracker.current_text
        )

    return True


def parse_log_thessi_odlast_gildi_d_m_y___(tracker: IntentTracker):
    match = re.match(
        r"Lög þessi (taka|öðlast) gildi (%s)( .*)?" % ICELANDIC_DATE_REGEX,
        tracker.current_text,
    )
    if match is None:
        return False

    _, raw_date, _, _, _, raw_extra = match.groups()
    timing = dateparser.parse(raw_date)
    extra = "" if raw_extra is None else raw_extra.strip()

    intent = tracker.make_enactment(timing, "immediate", extra)

    tracker.intents.append(intent)

    return True


def parse_log_thessi_odlast_gildi_med___(tracker: IntentTracker):
    match = re.match(r"Lög þessi öðlast gildi með (.+)", tracker.current_text)
    if match is None:
        return False

    extra = match.groups()[0]

    timing = dateparser.parse(
        tracker.original.getroottree().getroot().attrib["published-date"]
    )
    timing_type = "immediate"

    intent = tracker.make_enactment(
        timing,
        timing_type,
        extra=extra,
    )

    tracker.intents.append(intent)

    return True


def parse_log_thessi_odlast_thegar_gildi___(tracker: IntentTracker):
    # In this case, we'll be working with the text itself and no sub-content.
    text = tracker.current_text
    if not text.startswith("Lög þessi öðlast þegar gildi"):
        return False

    timing = dateparser.parse(
        tracker.original.getroottree().getroot().attrib["published-date"]
    )
    timing_type = "undetermined"
    implemented_timing = None
    implemented_timing_custom = ""

    if text == "Lög þessi öðlast þegar gildi.":
        timing_type = "immediate"
    elif (
        match := re.match(
            r"Lög þessi öðlast þegar gildi og( skulu)? koma til framkvæmda (.+)", text
        )
    ) is not None:
        implemented_timing_raw = match.groups()[1]
        implemented_timing = dateparser.parse(implemented_timing_raw)
        if implemented_timing is None:
            implemented_timing_custom = implemented_timing_raw
        timing_type = "immediate-with-delayed-implemention"

    intent = tracker.make_enactment(
        timing,
        timing_type,
        implemented_timing=implemented_timing,
        implemented_timing_custom=implemented_timing_custom,
    )

    tracker.intents.append(intent)

    return True


def parse_title_gildistaka(tracker: IntentTracker):
    match = re.match(r"Gildistaka\.", tracker.current_text)
    if not match:
        return False

    next(tracker.lines)

    if parse_group_enactments(tracker):
        pass
    else:
        raise IntentParsingException(
            "Don't know how to parse enactment: %s" % tracker.current_text
        )

    return True


def parse_thratt_fyrir_x_skal_x_odlast_gildi_d_m_y(tracker: IntentTracker):
    match = re.match(
        r"Þrátt fyrir (.+) skal (.+) öðlast gildi (%s)." % ICELANDIC_DATE_REGEX,
        tracker.current_text,
    )
    if match is None:
        return False

    address = match.groups()[1]
    timing = dateparser.parse(match.groups()[2])

    intent = tracker.make_enactment(timing, "specific", address=address)

    tracker.intents.append(intent)

    return True


def parse_group_enactments(tracker: IntentTracker):
    parsed = any(
        [
            parse_log_thessi_odlast_thegar_gildi___(tracker),
            parse_log_thessi_odlast_gildi_d_m_y___(tracker),
            parse_log_thessi_odlast_gildi_med___(tracker),
        ]
    )
    if not parsed:
        return False

    # On occasion, laws are repealed in the enactment clause.
    # Example:
    # - 17. gr. laga nr. 47/2024
    #   https://www.stjornartidindi.is/Advert.aspx?RecordID=5d38d4e5-bc5d-4761-bf3a-c565f39d4e61
    #
    # This search string is currently rather strict, but may need to become
    # more flexible later.
    #
    # NOTE: Normally we would place this in a separate parsing function, but it
    # happens in the same element as the text describing the enactment, so that
    # would require breaking the mold a bit. If this gets needed in
    # non-enactment clauses, we should definitely turn this into its own
    # parsing function, separate the enactment text into separate sentences
    # (using `separate_sentences`) and apply an independent parsing function.
    match = re.search(
        r"Við gildistöku laga þessara falla úr gildi ((.+) nr\. (\d{1,3}\/\d{4}))\.",
        tracker.current_text,
    )
    if match is not None:
        repealed_law_identifier = match.groups()[2]
        intent = tracker.make_repeal(repealed_law_identifier)
        tracker.intents.append(intent)

    # Check if there are special cases where individual clauses are not enacted
    # at the same time as the rest.
    if tracker.lines.peek() is not None:
        next(tracker.lines)
        parse_thratt_fyrir_x_skal_x_odlast_gildi_d_m_y(tracker)

    return True


def parse_outer_article(tracker: IntentTracker):
    # IMPORTANT: This function may only be called once every parsing function
    # that depends on an article's name has already been called. Otherwise,
    # this one will erroneously skip articles that have content-specific
    # parsers, such as for enactment or changes to other laws.

    # FIXME:
    # When content starts with the following, we will recognize it as article
    # content (i.e. not changing existing content). This is almost certainly a
    # temporary solution, as we are otherwise expecting outer articles to have
    # names, which is by no means a given. The proper way to go about doing
    # this, is scanning for any conceivable permutation of changing an existing
    # law, and then assuming that anything else is an outer article. However,
    # this cannot reasonably be achieved until we are confident in our
    # change-detecting being adequate. This may end up being partially manual.
    #
    # Occurs in:
    # - 2. gr. laga nr. 126/2024
    #   https://www.stjornartidindi.is/Advert.aspx?RecordID=bc93a573-99a3-48ad-8c05-04b8233c8078
    #   http://localhost:8001/althingi/parliament/155/document/348/
    name_free_indicators = [
        "Ríkisstjórninni er heimilt ",
    ]

    if not (
        tracker.lines.current.tag == "text"
        and (
            # FIXME: Explain why this `em` search is here.
            tracker.lines.current.find("em") is not None
            or any([tracker.current_text.startswith(s) for s in name_free_indicators])
        )
    ):
        return False

    # Ignoring for now. Later, this will add an article to an entirely new law.
    return True


def parse_ignorables(tracker: IntentTracker):
    """
    On occasion, a law primarily changing other laws will have a clause that
    doesn't end up in the final codex, except as a part of the change-law
    itself. We will ignore those.

    Example:
    - 3. gr. laga nr. 103/2024
      https://www.stjornartidindi.is/Advert.aspx?RecordID=412f2917-286f-4017-a061-39aef0493c55
    """
    ignorables = [
        r"(.+)skal prentuð sem fylgiskjal við tilkynningu utanríkisráðherra með auglýsingu í A-deild Stjórnartíðinda",
    ]
    for ignorable in ignorables:
        if re.match(ignorable, tracker.current_text) is not None:
            return True

    return False


def parse_intents_by_text_analysis(
    advert_tracker: AdvertTracker, original: _Element
) -> bool:

    tracker = IntentTracker(original)

    current_text = tracker.current_text

    if parse_a_b___(tracker):
        pass
    elif parse_a_eftir_ordinu_x_i_x_laganna_kemur(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_nyr_kafli_x_x_x_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_malsgrein_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_malslidur_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_grein_x_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_nyr_tolulidur_svohljodandi(tracker):
        pass
    elif parse_a_undan_x_laganna_kemur_ny_grein_x_svohljodandi(tracker):
        pass
    elif parse_eftirfarandi_breytingar_verda_a_x_laganna(tracker):
        pass
    elif parse_eftirfarandi_log_eru_felld_ur_gildi(tracker):
        pass
    elif parse_i_stad_ordanna_x_og_x_i_x_x_thrivegis_i_x_og_tvivegis_i_x_i_logunum_kemur_i_videigandi_beygingarmynd(
        tracker
    ):
        pass
    elif parse_i_stad_x_kemur_malslidur_svohljodandi(tracker):
        pass
    elif parse_i_stad_x_laganna_kemur_malsgrein_svohljodandi(tracker):
        pass
    elif (
        parse_i_stad_x_laganna_koma_fimm_nyjar_greinar_x_svohljodandi_asamt_fyrirsognum(
            tracker
        )
    ):
        pass
    elif parse_i_stad_x_i_x_kemur(tracker):
        pass
    elif parse_i_stad_hlutfallstolunnar_x_og_artalsins_x_tvivegis_i_x_i_logunum_kemur(
        tracker
    ):
        pass
    elif parse_ordin_x_i_x_laganna_falla_brott(tracker):
        pass
    elif parse_rikisborgararett_skulu_odlast(tracker):
        pass
    elif parse_tafla_i_x_laganna_ordast_svo(tracker):
        pass
    elif parse_vid_gildistoku_laga_thessara_verda_eftirfarandi_breytingar_a_odrum_logum(
        tracker
    ):
        pass
    elif parse_vid_gildistoku_laga_thessara_verda_eftirfarandi_breytingar_a_x_i_logum_um_x_nr_x(
        tracker
    ):
        pass
    elif parse_vid_gildistoku_laga_thessara_verda_eftirfarandi_breytingar_a_logum_nr_x(
        tracker
    ):
        pass
    elif parse_vid_gildistoku_laga_thessara_verdur_eftirfarandi_breyting_a_logum_nr_x(
        tracker
    ):
        pass
    elif parse_vid_login_baetast_tvo_ny_x_svohljodandi(tracker):
        pass
    elif parse_vid_login_baetist_nytt_x_svohljodandi(tracker):
        pass
    elif parse_vid_login_baetist_ny_grein_svohljodandi(tracker):
        pass
    elif parse_vid_login_baetist_ny_grein_x_svohljodandi(tracker):
        pass
    elif parse_vid_toflu_i_x_laganna_baetist(tracker):
        pass
    elif parse_vid_x_laganna_baetist_malslidur_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist_tolulidur_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist_nyr_tolulidur_x_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist(tracker):
        pass
    elif parse_vid_x_laganna_baetist_grein_x_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist_malsgrein_svohljodandi(tracker):
        pass
    elif parse_x_laganna_ordast_svo(tracker):
        pass
    elif parse_x_ordast_svo(tracker):
        pass
    elif parse_x_laganna_verdur(tracker):
        pass
    elif parse_x_nr_x_falla_ur_gildi(tracker):
        pass
    elif parse_x_laganna_faer_fyrirsogn_svohljodandi(tracker):
        pass
    elif parse_x_laganna_fellur_brott(tracker):
        pass
    elif parse_title_breyting_a_odrum_logum(tracker):
        pass
    elif parse_appendix_change(tracker):
        pass
    elif parse_title_gildistaka(tracker):
        pass
    elif parse_group_enactments(tracker):
        pass
    elif parse_outer_article(tracker):
        pass
    elif parse_ignorables(tracker):
        pass
    else:
        raise IntentParsingException("Can't figure out: %s" % current_text)

    advert_tracker.targets.art.append(tracker.intents)

    return True
