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
from datetime import datetime
from lagasafn.advert.tracker import AdvertTracker
from lagasafn.advert.intent.tracker import IntentTracker
from lagasafn.constants import ICELANDIC_DATE_REGEX
from lagasafn.constructors import construct_node
from lagasafn.contenthandlers import add_sentences
from lagasafn.contenthandlers import analyze_art_name
from lagasafn.contenthandlers import separate_sentences
from lagasafn.exceptions import IntentParsingException
from lagasafn.models.intent import IntentModelList
from lagasafn.pathing import make_xpath_from_node
from lagasafn.utils import determine_month
from lagasafn.utils import generate_legal_reference
from lagasafn.utils import get_all_text
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
        prompt = prompt.replace("{affected_law_year}", advert_tracker.affected["law-year"])

    xml_text = write_xml(original)

    client = OpenAI()

    completion = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Meðfylgjandi XML skjal 'remote.xml' er hér: %s" % xml_text },
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
    # TODO: Great candidate for merging with:
    #     parse_x_i_logunum_ordast_svo
    match = re.match(r"(.+) laganna orðast svo: ?(.+)?", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()

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
        next(tracker.lines)
        parse_inner_art_subart(tracker, {"nr": existing[0].attrib["nr"]})
    elif len(existing) == 1 and existing[0].tag == "numart":
        inner_node = existing[0]
        for inner_child in list(inner_node):
            inner_node.remove(inner_child)
        sentences = separate_sentences(text_to)
        add_sentences(inner_node, sentences)
    else:
        raise IntentParsingException("Don't know how to replace at address: %s" % address)

    tracker.targets.inner = None
    tracker.intents.append(intent)

    return True


def parse_x_i_logunum_ordast_svo(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_x_laganna_ordast_svo
    match = re.match(r"(.+) í lögunum orðast svo: ?(.+)?", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()

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
        parse_inner_art_subart(tracker, {"nr": existing[0].attrib["nr"]})
    elif len(existing) == 1 and existing[0].tag == "numart":
        inner_node = existing[0]
        for inner_child in list(inner_node):
            inner_node.remove(inner_child)
        sentences = separate_sentences(text_to)
        add_sentences(inner_node, sentences)
    else:
        raise IntentParsingException("Don't know how to replace at address: %s" % address)

    tracker.targets.inner = None
    tracker.intents.append(intent)

    return True


def parse_x_laganna_fellur_brott(tracker: IntentTracker):
    match = re.match(r"(.+) laganna fellur brott\.", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]

    tracker.intents.append(tracker.make_intent("delete", address))

    return True


def parse_x_i_logunum_falla_brott(tracker: IntentTracker):
    match = re.match(r"(.+) í lögunum falla brott.", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]

    tracker.intents.append(tracker.make_intent("delete", address))

    return True


def parse_x_laganna_falla_brott(tracker: IntentTracker):
    match = re.match(r"(.+) laganna falla brott.", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]

    tracker.intents.append(tracker.make_intent("delete", address))

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

    return False


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


def parse_inner_art_numarts(tracker: IntentTracker, ol: _Element | None = None):
    if ol is None:
        ol = tracker.lines.current

    if ol.tag != "ol":
        return False

    # Figure out the number type.
    nr_type = ""
    if (
            (
                "style" in ol.attrib
                and ol.attrib["style"] == "list-style-type: lower-alpha;"
            )
            or (
                "type" in ol.attrib
                and ol.attrib["type"] == "a"
            )
        ):
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
            {
                "nr": nr,
                "nr-type": nr_type
            },
            E("nr-title", nr_title),
        )
        if len(name) > 0:
            numart.append(E("name", name))

        add_sentences(numart, separate_sentences(text))

        sub_ols = li.xpath("ol")
        if len(sub_ols) > 0:
            tracker.inner_targets.numarts.append(numart)
            for sub_ol in sub_ols:
                parse_inner_art_numarts(tracker, sub_ol)
            tracker.inner_targets.numarts.pop()

        target.append(numart)

    # Check if there is a paragraph following the `ol`.
    if ol.tail.strip() != "":
        sentences = separate_sentences(ol.tail.strip())
        add_sentences(target.getparent(), sentences)

    return True


def parse_inner_art_subart(tracker: IntentTracker, prefilled: dict = {}):
    if not (
        "style" in tracker.lines.current.attrib
        and tracker.lines.current.attrib["style"] == "text-align: justify;"
    ):
        return False

    if "nr" in prefilled:
        nr = int(prefilled["nr"])
    else:
        # Figure out the number from existing `subart`s within the article.
        nr = len(tracker.inner_targets.art.findall("subart")) + 1

    tracker.inner_targets.subart = E("subart", { "nr": str(nr) })

    # Add sentences.
    sens = separate_sentences(get_all_text(tracker.lines.current))
    add_sentences(tracker.inner_targets.subart, sens)
    del sens

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
        tracker.lines.current.tag == "p"
        and (
            "style" not in tracker.lines.current.attrib
            or tracker.lines.current.attrib["style"] == "text-align: justify;"
        )
    ):
        return False

    match = re.match(r"([a-z]\. )?\((.+)\)", tracker.lines.current.text.strip())
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

    tracker.inner_targets.art.attrib["nr"] = nr
    tracker.inner_targets.art.find("nr-title").text = nr_title

    # Add Roman information if available.
    if len(roman_nr) > 0:
        tracker.inner_targets.art.attrib["roman-nr"] = roman_nr
        tracker.inner_targets.art.attrib["number-type"] = "roman"

    return True


def parse_inner_art(tracker: IntentTracker, prefilled: dict = {}):

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
    tracker.inner_targets.art = E("art", { "nr": nr })
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

        raise IntentParsingException("Don't know what to do with line: %s" % get_all_text(line))

    tracker.targets.inner.append(tracker.inner_targets.art)

    tracker.inner_targets.art = None

    return True


def parse_a_eftir_x_laganna_kemur_ny_malsgrein_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á eftir (.+) laganna kemur ný málsgrein, svohljóðandi", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]
    existing, xpath = tracker.get_existing_from_address(address)

    # Make the inner.
    tracker.targets.inner = E("inner")

    if existing.tag == "subart":
        action_node = existing
        action_xpath = make_xpath_from_node(action_node)
    else:
        raise IntentParsingException("Don't know how to add subart to tag: %s" % existing.tag)

    # Make the intent.
    tracker.intents.append(E(
        "intent",
        {
            "action": "append",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        tracker.targets.inner,
    ))

    nr = int(existing.attrib["nr"])
    for line in tracker.lines:
        nr += 1
        parse_inner_art_subart(tracker, {"nr": nr })

    tracker.targets.inner = None

    return True


def parse_vid_x_laganna_baetast_tvaer_nyjar_malsgreinar_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_a_eftir_x_laganna_kemur_ny_malsgrein_svohljodandi
    #     parse_vid_x_laganna_baetist_ny_malsgrein_svohljodandi
    #     parse_vid_x_laganna_baetast_thrjar_nyjar_malsgreinar_svohljodandi
    match = re.match(r"Við (.+) laganna bætast tvær nýjar málsgreinar, svohljóðandi:", tracker.current_text)
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
            parse_inner_art_subart(tracker, {"nr": nr })

    else:
        raise IntentParsingException("Don't know how to add subart at address: %s" % address)

    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)
    tracker.targets.inner = None

    return True


def parse_vid_x_laganna_baetast_thrjar_nyjar_malsgreinar_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_a_eftir_x_laganna_kemur_ny_malsgrein_svohljodandi
    #     parse_vid_x_laganna_baetist_ny_malsgrein_svohljodandi
    #     parse_vid_x_laganna_baetast_tvaer_nyjar_malsgreinar_svohljodandi
    match = re.match(r"Við (.+) laganna bætast þrjár nýjar málsgreinar, svohljóðandi:", tracker.current_text)
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
            parse_inner_art_subart(tracker, {"nr": nr })

    else:
        raise IntentParsingException("Don't know how to add subart at address: %s" % address)

    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)
    tracker.targets.inner = None

    return True


def parse_vid_x_laganna_baetist_ny_malsgrein_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_a_eftir_x_laganna_kemur_ny_malsgrein_svohljodandi
    #     parse_vid_x_laganna_baetast_thrjar_nyjar_malsgreinar_svohljodandi
    match = re.match(r"Við (.+) laganna bætist ný málsgrein, svohljóðandi:", tracker.current_text)
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
            parse_inner_art_subart(tracker, {"nr": nr })

    else:
        raise IntentParsingException("Don't know how to add subart at address: %s" % address)

    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)
    tracker.targets.inner = None

    return True


def parse_vid_x_i_logunum_baetist_ny_malsgrein_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_a_eftir_x_laganna_kemur_ny_malsgrein_svohljodandi
    #     parse_vid_x_laganna_baetast_thrjar_nyjar_malsgreinar_svohljodandi
    #     parse_vid_x_laganna_baetist_ny_malsgrein_svohljodandi
    match = re.match(r"Við (.+) í lögunum bætist ný málsgrein, svohljóðandi:", tracker.current_text)
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
            parse_inner_art_subart(tracker, {"nr": nr })

    else:
        raise IntentParsingException("Don't know how to add subart at address: %s" % address)

    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)
    tracker.targets.inner = None

    return True


def parse_sub_i_stad_ordsins_x_i_x_kemur(tracker: IntentTracker, li: _Element):
    match = re.match(r"Í stað orðsins „(.+)“ í (.+) kemur: (.+)", get_all_text(li))
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("replace_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_sub_i_stad_ordsins_x_tvivegis_i_x_kemur(tracker: IntentTracker, li: _Element):
    match = re.match(r"Í stað orðsins „(.+)“ tvívegis í (.+) kemur: (.+)", get_all_text(li))
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("replace_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_sub_i_stad_ordsins_x_tvivegis_i_x_og_einu_sinni_i_x_kemur(tracker: IntentTracker, li: _Element):
    match = re.match(r"Í stað orðins „(.+)“ tvívegis í (.+) og einu sinni í (.+) kemur: (.+)", get_all_text(li))
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


def parse_sub_a_undan_ordunum_x_i_x_kemur(tracker: IntentTracker, li: _Element):
    match = re.match(r"Á undan orðunum „(.+)“ í (.+) kemur: (.+)", get_all_text(li))
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("prepend_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_sub_a_undan_x_kemur_nyr_tolulidur(tracker: IntentTracker, li: _Element):
    match = re.match(r"Á undan (.+) kemur nýr töluliður, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("prepend", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "numart":
        inner.append(construct_node(existing[0], text_to, nr_change=0))
    else:
        raise IntentParsingException("Don't know how to prepend numart at address: %s" % address)

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_sub_i_stad_ordanna_x_i_x_kemur(tracker: IntentTracker, li: _Element):
    # TODO: Great candidate for merging with:
    #     parse_sub_i_stad_ordanna_x
    #     parse_sub_i_stad_tilvisunarinnar_x_i_x_kemur
    match = re.match(r"Í stað orðanna „(.+)“ í (.+) kemur: (.+)", get_all_text(li))
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("replace_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_sub_i_stad_ordanna_x(tracker: IntentTracker, li: _Element):
    # TODO: Great candidate for merging with:
    #     parse_sub_i_stad_ordanna_x_i_x_kemur
    #     parse_sub_i_stad_tilvisunarinnar_x_i_x_kemur
    match = re.match(r"Í stað orðanna „(.+)“ kemur: (.+)", get_all_text(li))
    if match is None:
        return False

    text_from, text_to = match.groups()

    intent = tracker.make_intent("replace_text", "")
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_sub_i_stad_tilvisunarinnar_x_i_x_kemur(tracker: IntentTracker, li: _Element):
    # TODO: Great candidate for merging with:
    #     parse_sub_i_stad_ordanna_x_i_x_kemur
    #     parse_sub_i_stad_ordanna_x
    match = re.match(r"Í stað tilvísunarinnar „(.+)“ í (.+) kemur: (.+)", get_all_text(li))
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("replace_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_sub_a_eftir_ordinu_x_i_x_kemur(tracker: IntentTracker, li: _Element):
    match = re.match(r"Á eftir orðinu „(.+)“ í (.+) kemur: (.+)", get_all_text(li))
    if match is None:
        return False

    text_from, address, text_to = match.groups()
    address = "%s %s" % (address, tracker.intents.attrib["common-address"])
    existing, xpath = tracker.get_existing_from_address(address)
    action_xpath = make_xpath_from_node(existing)

    tracker.intents.append(E(
        "intent",
        {
            "action": "append_text",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("text-from", text_from),
        E("text-to", text_to),
    ))

    return True


def parse_sub_a_eftir_ordunum_x_i_x_kemur(tracker: IntentTracker, li: _Element):
    match = re.match(r"Á eftir orðunum „(.+)“ í (.+) kemur: (.+)", get_all_text(li))
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("append_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_sub_a_eftir_x_kemur_nyr_tolulidur_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Á eftir (.+) kemur nýr töluliður, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "numart":
        inner.append(construct_node(existing[0], text_to))
    else:
        raise IntentParsingException("Don't know how to append numart at address: %s" % address)

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_sub_a_eftir_x_kemur_ny_malsgrein_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Á eftir (.+) kemur ný málsgrein, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("append", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "subart":
        inner.append(construct_node(existing[0], text_to))
    else:
        raise IntentParsingException("Don't know how to append subart at address: %s" % address)

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_sub_vid_x_baetist(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við (.+) bætist: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("add_text", address)
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_sub_ordin_x_falla_brott(tracker: IntentTracker, li: _Element):
    match = re.match(r"Orðin „(.+)“ falla brott\.", get_all_text(li))
    if match is None:
        return False

    address = ""
    text_from = match.groups()[0]

    intent = tracker.make_intent("delete_text", address)
    intent.append(E("text-from", text_from))

    tracker.intents.append(intent)

    return True


def parse_sub_x_falla_brott(tracker: IntentTracker, li: _Element):
    match = re.match(r"(.+) falla brott\.", get_all_text(li))
    if match is None:
        return False

    address = match.groups()[0]

    tracker.intents.append(tracker.make_intent("delete", address))

    return True


def parse_sub_x_fallur_brott(tracker: IntentTracker, li: _Element):
    match = re.match(r"(.+) fellur brott\.", get_all_text(li))
    if match is None:
        return False

    address = match.groups()[0]

    tracker.intents.append(tracker.make_intent("delete", address))

    return True


def parse_sub_ordid_x_i_x_fellur_brott(tracker: IntentTracker, li: _Element):
    match = re.match(r"Orðið „(.+)“ í (.+) fellur brott.", get_all_text(li))
    if match is None:
        return False

    text_from, address = match.groups()

    intent = tracker.make_intent("delete_text", address)
    intent.append(E("text-from", text_from))

    tracker.intents.append(intent)

    return True


def parse_sub_vid_x_baetast_tveir_nyir_malslidir_svohljodandi(tracker: IntentTracker, li: _Element):
    # TODO: Great candidate for merging with:
    #     parse_vid_x_laganna_baetist_nyr_malslidur_svohljodandi
    #     parse_sub_vid_baetist_nyr_malslidur_svohljodandi
    match = re.match(r"Við (.+) bætast tveir nýir málsliðir, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("add", address, "sen")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["numart", "subart"]:
        nr = len(existing[0].xpath("paragraph")[-1])
        sentences = separate_sentences(text_to)
        for sentence in sentences:
            nr += 1
            inner.append(E("sen", {"nr": str(nr) }, sentence))
    else:
        raise IntentParsingException("Don't know how to add sentence at address: %s" % address)

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_sub_vid_x_baetist_nyr_malslidur_svohljodandi(tracker: IntentTracker, li: _Element):
    # TODO: Great candidate for merging with (currently identical):
    #     parse_sub_vid_x_baetast_tveir_nyir_malslidir_svohljodandi
    #     parse_sub_vid_baetist_nyr_malslidur_svohljodandi
    match = re.match(r"Við (.+) bætist nýr málsliður, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("add", address, "sen")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["numart", "subart"]:
        nr = len(existing[0].xpath("paragraph")[-1])
        sentences = separate_sentences(text_to)
        for sentence in sentences:
            nr += 1
            inner.append(E("sen", {"nr": str(nr) }, sentence))
    else:
        raise IntentParsingException("Don't know how to add sentence at address: %s" % address)

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_sub_vid_baetist_nyr_malslidur_svohljodandi(tracker: IntentTracker, li: _Element):
    # TODO: Great candidate for merging with:
    #     parse_sub_vid_x_baetast_tveir_nyir_malslidir_svohljodandi
    #     parse_sub_vid_x_baetist_nyr_malslidur_svohljodandi
    #     parse_sub_vid_baetast_tveir_nyir_malslidir_svohljodandi
    match = re.match(r"Við bætist nýr málsliður, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address = ""
    text_to = match.groups()[0]

    intent = tracker.make_intent("add", address, "sen")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["art"]:
        nr = len(existing[0].xpath("//paragraph")[-1].findall("sen"))
        sentences = separate_sentences(text_to)
        for sentence in sentences:
            nr += 1
            inner.append(E("sen", {"nr": str(nr) }, sentence))
    else:
        raise IntentParsingException(
            "Don't know how to add sentence at address: %s" % tracker.intents.attrib["common-address"]
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_sub_vid_baetast_tveir_nyir_malslidir_svohljodandi(tracker: IntentTracker, li: _Element):
    # TODO: Great candidate for merging with:
    #     parse_sub_vid_x_baetast_tveir_nyir_malslidir_svohljodandi
    #     parse_sub_vid_x_baetist_nyr_malslidur_svohljodandi
    #     parse_sub_vid_baetist_nyr_malslidur_svohljodandi
    match = re.match(r"Við bætast tveir nýir málsliðir, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address = ""
    text_to = match.groups()[0]

    intent = tracker.make_intent("add", address, "sen")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["art", "subart"]:
        nr = len(existing[0].xpath("//paragraph")[-1].findall("sen"))
        sentences = separate_sentences(text_to)
        for sentence in sentences:
            nr += 1
            inner.append(E("sen", {"nr": str(nr) }, sentence))
    else:
        raise IntentParsingException(
            "Don't know how to add sentence at address: %s" % tracker.intents.attrib["common-address"]
        )

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_sub_vid_baetast_tveir_nyir_tolulidir_sem_verda_x_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við bætast tveir nýir töluliðir, sem verða (.+), svohljóðandi:", get_all_text(li))
    if match is None:
        return False

    address = ""

    intent = tracker.make_intent("insert", address)
    existing = deepcopy(list(intent.find("existing")))

    tracker.targets.inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "subart":
        for ol in li.xpath("ol"):
            parse_inner_art_numarts(tracker, ol)
    else:
        raise IntentParsingException(
            "Don't know how to add numart at address: %s" % tracker.intents.attrib["common-address"]
        )

    intent.append(tracker.targets.inner)
    tracker.intents.append(intent)

    return True


def parse_sub_vid_baetist_ny_malsgrein_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við bætist ný málsgrein, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    text_to = match.groups()[0]
    address = tracker.intents.attrib["common-address"]
    existing, xpath = tracker.get_existing_from_address(address)

    inner = E("inner")
    if existing.tag == "art":
        action_node = existing
        action_xpath = make_xpath_from_node(action_node)

        # When added to an `art`, then "málsgrein" means a `subart`, not a
        # `paragraph`. This is only because the file format makes a distinction
        # between a `subart` and `paragraph`, but the human language doesn't.
        subart_nr = len(existing.xpath("subart")) + 1
        subart = E("subart", {"nr": str(subart_nr) })

        sens = separate_sentences(text_to)
        add_sentences(subart, sens)

        inner.append(subart)
    else:
        raise IntentParsingException("Don't know how to add paragraph to tag: %s" % existing.tag)

    # NOTE: The address isn't specified here. It will be in the parent node.
    tracker.intents.append(E(
        "intent",
        {
            "action": "add",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        inner,
    ))

    return True


def parse_sub_vid_baetist_nyr_tolulidur_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við bætist nýr töluliður, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address = ""
    text_to = match.groups()[0]

    intent = tracker.make_intent("add", address, node_hint="numart")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag == "subart":
        base_numart = existing[0].xpath("//numart")[-1]
        inner.append(construct_node(base_numart, text_to))
    else:
        raise IntentParsingException("Don't know how to add numart at address: %s" % address)

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_sub_fyrirsogn_greinarinnar_ordast_svo(tracker: IntentTracker, li: _Element):
    match = re.match(r"Fyrirsögn greinarinnar orðast svo: (.+)", get_all_text(li))
    if match is None:
        return False

    address = ""
    name = match.groups()[0]

    intent = tracker.make_intent("replace", address, "name")

    inner = E("inner", E("name", name))

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_sub_fyrirsogn_greinarinnar_verdur(tracker: IntentTracker, li: _Element):
    match = re.match(r"Fyrirsögn greinarinnar verður: (.+)", get_all_text(li))
    if match is None:
        return False

    address = ""
    name = match.groups()[0]

    intent = tracker.make_intent("replace", address, "name")

    inner = E("inner", E("name", name))

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_sub_x_ordast_svo(tracker: IntentTracker, li: _Element):
    match = re.match(r"(.+) orðast svo: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("replace", address)
    inner = deepcopy(list(intent.find("existing")))

    intent.append(E("inner", *inner))
    tracker.intents.append(intent)

    if len(inner) == 1 and inner[0].tag in ["numart", "subart"]:
        inner_node = inner[0]
        for paragraph in list(inner_node):
            inner_node.remove(paragraph)
        inner.append(add_sentences(inner_node, separate_sentences(text_to)))
        del inner_node

    elif len(inner) > 0 and all([i.tag == "sen" for i in inner]):
        sentences = separate_sentences(text_to)

        if len(sentences) != len(inner):
            raise IntentParsingException(
                "Unimplemented: Replacing a number of sentences with a different amount of sentences."
            )

        for i, sentence in enumerate(sentences):
            inner[i].text = sentence

    else:
        raise IntentParsingException("Don't know how to replace content at address: %s" % address)

    return True


def parse_sub_tafla_i_x_ordast_svo(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_tafla_i_x_laganna_ordast_svo
    match = re.match(r"([a-z])\. (Tafla í (.+)) orðast svo:", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[1]
    address = "%s %s" % (address, tracker.intents.attrib["common-address"])
    existing, xpath = tracker.get_existing_from_address(address)
    action_xpath = make_xpath_from_node(existing)

    tracker.targets.inner = E("inner")

    next(tracker.lines)

    parse_inner_table(tracker)

    intent = E(
        "intent",
        {
            "action": "replace",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        tracker.targets.inner,
    )
    tracker.intents.append(intent)

    tracker.targets.inner = None

    return True


def parse_tafla_i_x_laganna_ordast_svo(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_sub_tafla_i_x_ordast_svo
    match = re.match(r"(Tafla í (.+)) laganna orðast svo:", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]
    existing, xpath = tracker.get_existing_from_address(address)
    action_xpath = make_xpath_from_node(existing)

    next(tracker.lines)

    tracker.targets.inner = E("inner")

    parse_inner_table(tracker)

    intent = E(
        "intent",
        {
            "action": "replace",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("inner", tracker.targets.inner),
    )
    tracker.intents.append(intent)

    tracker.targets.inner = None

    return True


def parse_eftirfarandi_breytingar_verda_a_x_laganna(tracker: IntentTracker):
    # NOTE: That questionable space at the end happens occurs in advert 45/2024.
    match = re.match(r"Eftirfarandi breytingar verða á (.+) laganna ?:", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]
    tracker.intents.attrib["common-address"] = address

    # Because we need to iterate by different means, depending on the nature of
    # the content, we need to check the next item, rather than the current one,
    # to determine how to iterate.
    if tracker.lines.peek().tag == "ol":
        next(tracker.lines)
        for li in tracker.lines.current.findall("li"):

            if parse_sub_i_stad_ordsins_x_i_x_kemur(tracker, li):
                pass
            elif parse_sub_i_stad_ordsins_x_tvivegis_i_x_kemur(tracker, li):
                pass
            elif parse_sub_i_stad_ordsins_x_tvivegis_i_x_og_einu_sinni_i_x_kemur(tracker, li):
                pass
            elif parse_sub_a_undan_ordunum_x_i_x_kemur(tracker, li):
                pass
            elif parse_sub_a_undan_x_kemur_nyr_tolulidur(tracker, li):
                pass
            elif parse_sub_i_stad_ordanna_x_i_x_kemur(tracker, li):
                pass
            elif parse_sub_i_stad_ordanna_x(tracker, li):
                pass
            elif parse_sub_i_stad_tilvisunarinnar_x_i_x_kemur(tracker, li):
                pass
            elif parse_sub_a_eftir_ordinu_x_i_x_kemur(tracker, li):
                pass
            elif parse_sub_a_eftir_ordunum_x_i_x_kemur(tracker, li):
                pass
            elif parse_sub_a_eftir_x_kemur_nyr_tolulidur_svohljodandi(tracker, li):
                pass
            elif parse_sub_a_eftir_x_kemur_ny_malsgrein_svohljodandi(tracker, li):
                pass
            elif parse_sub_vid_x_baetist(tracker, li):
                pass
            elif parse_sub_ordin_x_falla_brott(tracker, li):
                pass
            elif parse_sub_x_falla_brott(tracker, li):
                pass
            elif parse_sub_x_fallur_brott(tracker, li):
                pass
            elif parse_sub_ordid_x_i_x_fellur_brott(tracker, li):
                pass
            elif parse_sub_vid_x_baetast_tveir_nyir_malslidir_svohljodandi(tracker, li):
                pass
            elif parse_sub_vid_baetist_nyr_malslidur_svohljodandi(tracker, li):
                pass
            elif parse_sub_vid_baetast_tveir_nyir_malslidir_svohljodandi(tracker, li):
                pass
            elif parse_sub_vid_baetast_tveir_nyir_tolulidir_sem_verda_x_svohljodandi(tracker, li):
                pass
            elif parse_sub_vid_x_baetist_nyr_malslidur_svohljodandi(tracker, li):
                pass
            elif parse_sub_vid_baetist_ny_malsgrein_svohljodandi(tracker, li):
                pass
            elif parse_sub_vid_baetist_nyr_tolulidur_svohljodandi(tracker, li):
                pass
            elif parse_sub_fyrirsogn_greinarinnar_ordast_svo(tracker, li):
                pass
            elif parse_sub_fyrirsogn_greinarinnar_verdur(tracker, li):
                pass
            elif parse_sub_x_ordast_svo(tracker, li):
                pass
            else:
                raise IntentParsingException("Can't figure out list text: %s" % get_all_text(li))

    elif tracker.lines.peek().tag == "p":
        for _ in tracker.lines:
            if parse_sub_tafla_i_x_ordast_svo(tracker):
                continue

            raise IntentParsingException("Don't know how to parse p-element: %s" % get_all_text(tracker.lines.peek()))
    else:
        raise IntentParsingException("Unexpected tag for sub-change: %s" % tracker.lines.peek().tag)

    return True


def parse_vid_x_laganna_baetist_nyr_malslidur_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_vid_x_laganna_baetast_tveir_nyir_malslidir_svohljodandi
    match = re.match(r"Við (.+) laganna bætist nýr málsliður, svohljóðandi: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("add", address, "sen")
    existing = deepcopy(list(intent.find("existing")))  # Only doing `deepcopy` for consistency, it's unnecessary.

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["numart", "subart"]:
        nr = len(existing[0].xpath("paragraph")[-1])
        sentences = separate_sentences(text_to)
        for sentence in sentences:
            nr += 1
            inner.append(E("sen", {"nr": str(nr) }, sentence))
    else:
        raise IntentParsingException("Don't know how to add sentence at address: %s" % address)

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_vid_x_laganna_baetast_tveir_nyir_malslidir_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_vid_x_laganna_baetist_nyr_malslidur_svohljodandi
    match = re.match(r"Við (.+) laganna bætast tveir nýir málsliðir, svohljóðandi: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("add", address, "sen")
    existing = deepcopy(list(intent.find("existing")))  # Only doing `deepcopy` for consistency, it's unnecessary.

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["numart", "subart"]:
        nr = len(existing[0].xpath("paragraph")[-1])
        sentences = separate_sentences(text_to)
        for sentence in sentences:
            nr += 1
            inner.append(E("sen", {"nr": str(nr) }, sentence))
    else:
        raise IntentParsingException("Don't know how to add sentence at address: %s" % address)

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_a_eftir_x_laganna_kemur_ny_grein_x_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with identical function:
    #     parse_a_eftir_x_laganna_kemur_ny_grein_x_asamt_fyrirsogn_svohljodandi
    match = re.match(r"Á eftir (.+) laganna kemur ný grein, (.+), svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    address, nr_title_new = match.groups()
    existing, xpath = tracker.get_existing_from_address(address)

    if existing.tag == "art":
        action_node = existing
        action_xpath = make_xpath_from_node(action_node)
    else:
        raise IntentParsingException("Don't know how to append article after tag: %s" % existing.tag)

    intent = E(
        "intent",
        {
            "action": "append",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
    )
    tracker.intents.append(intent)

    tracker.targets.inner = E("inner")

    parse_inner_art(tracker, {
        "nr_title": nr_title_new,
    })

    intent.append(tracker.targets.inner)
    tracker.targets.inner = None

    return True


def parse_a_undan_x_laganna_kemur_ny_grein_x_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á undan (.+) laganna kemur ný grein, (.+), svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    address, nr_title = match.groups()
    existing, xpath = tracker.get_existing_from_address(address)

    if existing.tag == "art":
        action_node = existing
        action_xpath = make_xpath_from_node(action_node)
    else:
        raise IntentParsingException("Don't know how to prepend article to tag: %s" % existing.tag)

    intent = E(
        "intent",
        {
            "action": "prepend",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath}, address),
        E("existing", existing),
    )
    tracker.intents.append(intent)

    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    parse_inner_art(tracker, {"nr_title": nr_title })

    tracker.targets.inner = None

    return True


def parse_a_eftir_tilvisuninni_x_i_x_laganna_kemur(tracker: IntentTracker):
    match = re.match(r"Á eftir tilvísuninni „(.+)“ í (.+) laganna kemur: (.+)", tracker.current_text)
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("append_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_a_eftir_ordunum_x_i_x_laganna_kemur(tracker: IntentTracker):
    match = re.match(r"Á eftir orðunum „(.+)“ í (.+) laganna kemur: (.+)", tracker.current_text)
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("append_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_a_eftir_ordinu_x_i_x_laganna_kemur(tracker: IntentTracker):
    match = re.match(r"Á eftir orðinu „(.+)“ í (.+) laganna kemur: (.+)", tracker.current_text)
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("append_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_a_eftir_x_laganna_kemur_nyr_tolulidur_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á eftir (.+) laganna kemur nýr töluliður, svohljóðandi: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()
    existing, xpath = tracker.get_existing_from_address(address)

    if existing.tag == "numart":
        action_node = existing
        action_xpath = make_xpath_from_node(action_node)

        base_numart = action_node
    else:
        raise IntentParsingException("Don't know how to add numart to tag: %s" % existing.tag)

    name = ""
    if (em := tracker.lines.current.find("em")) is not None:
        name = em.text
        text_to = em.tail.strip()

    tracker.inner_targets.numarts.append(
        construct_node(base_numart, text_to, name)
    )

    next(tracker.lines)

    # This will either happen once or not at all, judging from "nýr töluliður"
    # being in the singular above.
    # Occurs in:
    # - 1. gr. laga nr. 48/2024
    parse_inner_art_numarts(tracker)

    tracker.intents.append(E(
        "intent",
        {
            "action": "append",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("inner", tracker.inner_targets.numarts[-1]),
    ))

    tracker.inner_targets.numarts.pop()

    return True


def parse_vid_x_laganna_baetist(tracker: IntentTracker):
    match = re.match(r"Við (.+) laganna bætist: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("add_text", address)
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_i_stad_x_laganna_kemur_einn_nyr_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Í stað (.+) laganna kemur einn nýr málsliður, svohljóðandi: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("replace", address)
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) > 0 and all([n.tag == "sen" for n in existing]):
        nr = existing[0].attrib["nr"]
        sen = E("sen", {"nr": nr }, text_to)
        inner.append(sen)
    else:
        raise IntentParsingException("Don't know how to replace unsupported tags at address %s" % address)

    intent.append(inner)

    tracker.intents.append(intent)

    return True

def parse_i_stad_ordanna_x_i_x_laganna_kemur(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_i_stad_fjarhaedarinnar_x_i_x_laganna_kemur
    #     parse_i_stad_ordsins_x_i_x_laganna_kemur
    #     parse_i_stad_ordsins_x_tvivegis_i_x_laganna_kemur
    match = re.match(r"Í stað orðanna „(.+)“ í (.+) laganna kemur: (.+)", tracker.current_text)
    if match is None:
        return False

    text_from, address, text_to = match.groups()
    existing, xpath = tracker.get_existing_from_address(address)
    action_xpath = make_xpath_from_node(existing)

    tracker.intents.append(E(
        "intent",
        {
            "action": "replace_text",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath}, address),
        E("existing", existing),
        E("text-from", text_from),
        E("text-to", text_to),
    ))

    return True


def parse_i_stad_ordsins_x_i_x_laganna_kemur(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_i_stad_fjarhaedarinnar_x_i_x_laganna_kemur
    #     parse_i_stad_ordanna_x_i_x_laganna_kemur
    #     parse_i_stad_ordsins_x_tvivegis_i_x_laganna_kemur
    match = re.match(r"Í stað orðsins „(.+)“ í (.+) laganna kemur: (.+)", tracker.current_text)
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("replace_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_i_stad_ordsins_x_tvivegis_i_x_laganna_kemur(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_i_stad_fjarhaedarinnar_x_i_x_laganna_kemur
    #     parse_i_stad_ordanna_x_i_x_laganna_kemur
    #     parse_i_stad_ordsins_x_i_x_laganna_kemur
    match = re.match(r"Í stað orðsins „(.+)“ tvívegis í (.+) laganna kemur: (.+)", tracker.current_text)
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("replace_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_i_stad_hlutfallstolunnar_x_og_artalsins_x_tvivegis_i_x_i_logunum_kemur(tracker: IntentTracker):
    match = re.match(r"Í stað hlutfallstölunnar „(.+)“ og ártalsins „(.+)“ tvívegis í (.+) í lögunum kemur: (.+); og: (.+)", tracker.current_text)
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


def parse_i_stad_fjarhaedarinnar_x_i_x_laganna_kemur(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_i_stad_ordanna_x_i_x_laganna_kemur
    #     parse_i_stad_ordsins_x_i_x_laganna_kemur
    #     parse_i_stad_ordsins_x_tvivegis_i_x_laganna_kemur
    #     parse_i_stad_tilvisunarinnar_x_i_x_laganna_kemur
    match = re.match(r"Í stað fjárhæðarinnar „(.+)“ í (.+) laganna kemur: (.+)", tracker.current_text)
    if match is None:
        return False

    text_from, address, text_to = match.groups()
    existing, xpath = tracker.get_existing_from_address(address)
    action_xpath = make_xpath_from_node(existing)

    tracker.intents.append(E(
        "intent",
        {
            "action": "replace_text",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath}, address),
        E("existing", existing),
        E("text-from", text_from),
        E("text-to", text_to),
    ))

    return True


def parse_i_stad_tilvisunarinnar_x_i_x_laganna_kemur(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_i_stad_ordanna_x_i_x_laganna_kemur
    #     parse_i_stad_ordsins_x_i_x_laganna_kemur
    #     parse_i_stad_ordsins_x_tvivegis_i_x_laganna_kemur
    #     parse_i_stad_fjarhaedarinnar_x_i_x_laganna_kemur
    match = re.match(r"Í stað tilvísunarinnar „(.+)“ í (.+) laganna kemur: (.+)", tracker.current_text)
    if match is None:
        return False

    text_from, address, text_to = match.groups()

    intent = tracker.make_intent("replace_text", address)
    intent.append(E("text-from", text_from))
    intent.append(E("text-to", text_to))

    tracker.intents.append(intent)

    return True


def parse_a_eftir_x_laganna_kemur_ny_grein_x_asamt_fyrirsogn_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á eftir (.+) laganna kemur ný grein, (.+), ásamt fyrirsögn, svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    address, nr_title_new = match.groups()
    existing, xpath = tracker.get_existing_from_address(address)
    action_xpath = make_xpath_from_node(existing)

    intent = E(
        "intent",
        {
            "action": "append",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
    )
    tracker.intents.append(intent)

    inner = E("inner")
    intent.append(inner)
    tracker.targets.inner = inner

    parse_inner_art(tracker, {
        "nr_title": nr_title_new,
    })

    tracker.targets.inner = None

    return True


def parse_a_eftir_x_laganna_koma_tvaer_nyjar_greinar_x_og_x_svohljodandi(tracker: IntentTracker):
    # While it is no doubt tempting to parse the amount of articles being added
    # here, we'll start doing it this way so that it's more resilient parsing
    # the new `art-nr`s as well. May very well change once we have a more
    # exhaustive list of possible additions.
    # TODO: Great candidate for merging with functions:
    #     parse_a_eftir_x_laganna_kemur_ny_grein_x_svohljodandi
    #     parse_a_eftir_x_laganna_kemur_ny_grein_x_asamt_fyrirsogn_svohljodandi
    match = re.match(r"Á eftir (.+) laganna koma tvær nýjar greinar, (.+) og (.+), svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]
    existing, xpath = tracker.get_existing_from_address(address)

    if existing.tag == "art":
        action_node = existing
        action_xpath = make_xpath_from_node(action_node)
    else:
        raise IntentParsingException("Don't know how to append article after tag: %s" % existing.tag)

    intent = E(
        "intent",
        {
            "action": "append",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing)
    )
    tracker.intents.append(intent)

    tracker.targets.inner = E("inner")

    parse_inner_art(tracker)
    parse_inner_art(tracker)

    intent.append(tracker.targets.inner)
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
    existing, xpath = tracker.get_existing_from_address(address)

    action_node = existing
    action_xpath = make_xpath_from_node(action_node)

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

    intent = E(
        "intent",
        {
            "action": "append",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath}, address),
        E("existing", existing),
    )
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

    match = re.match(r"Við lögin bætist ný grein, (.+), svohljóðandi:", tracker.current_text)
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
    existing, xpath = tracker.get_existing_from_address(address)

    if existing.tag == "art":
        action_node = existing
        action_xpath = make_xpath_from_node(action_node)
    else:
        raise IntentParsingException("Don't know how to append article to tag %s" % existing.tag)

    intent = E(
        "intent",
        {
            "action": "append",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
    )
    tracker.intents.append(intent)

    tracker.targets.inner = E("inner")
    intent.append(tracker.targets.inner)

    parse_inner_art(tracker, {"nr_title": nr_title})

    tracker.targets.inner = None

    return True


def parse_vid_login_baetast_tvö_ny_akvaedi_til_bradabirgda_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Við lögin bætast tvö ný ákvæði til bráðabirgða, svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    existing = tracker.get_existing("/law")
    action_xpath = make_xpath_from_node(existing)  # Currently always "".

    # Currently assuming that chapters exist whenever this happens. If this
    # assumption is wrong, then we'll need to implement support for adding a
    # new temporary clause chapter here someplace.
    action_node = tracker.get_existing("chapter[@nr-type='temporary-clauses']")
    action_xpath = make_xpath_from_node(action_node)

    # We don't seem able to trust that Roman numerals for new temporary clauses
    # are going to be correct. They may say "I" and "II" instead of "LXXX" and
    # "LXXXI", neglecting the numbering of already existing temporary articles.
    #
    # So we'll have to deduce the correct numbers from the existing content.
    #
    # Examples:
    # - 1. gr. laga nr. 36/2024:
    #   https://www.stjornartidindi.is/Advert.aspx?RecordID=8f772076-5dac-4bb0-baf1-1ee4a678e4a5
    #   https://www.althingi.is/altext/154/s/1619.html
    last_art_nr = int(action_node.xpath("art")[-1].attrib["roman-nr"])

    tracker.targets.inner = E("inner")

    parse_inner_art(tracker, prefilled={"nr_title": "%s." % roman.toRoman(last_art_nr+1)})
    parse_inner_art(tracker, prefilled={"nr_title": "%s." % roman.toRoman(last_art_nr+2)})

    tracker.intents.append(E(
        "intent",
        {
            "action": "add",
            "action-xpath": action_xpath,
        },
        tracker.targets.inner,
    ))

    tracker.targets.inner = None

    return True


def parse_akvaedi_til_bradabirgda_x_i_logunum_fellur_brott(tracker: IntentTracker):
    match = re.match(r"(Ákvæði til bráðabirgða ([A-Z]+)) í lögunum fellur brott.", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]
    existing, xpath = tracker.get_existing_from_address(address)

    if existing.tag == "art":
        action_node = existing
        action_xpath = make_xpath_from_node(action_node)
    else:
        raise IntentParsingException("Don't know how to delete temporary clause with tag: %s" % existing.tag)

    tracker.intents.append(E(
        "intent",
        {
            "action": "delete",
            "action-xpath": action_xpath
        },
        E("existing", existing),
    ))

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


def parse_a_eftir_x_laganna_kemur_nyr_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á eftir (.+) laganna kemur nýr málsliður, svohljóðandi: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()
    existing, xpath = tracker.get_existing_from_address(address)

    inner = E("inner")
    if existing.tag == "sen":
        action_node = existing
        action_xpath = make_xpath_from_node(action_node)

        # A temporary paragraph is created only to manipulate the newly created
        # sentences before adding them to the `inner`.
        paragraph = E("paragraph")
        sens = separate_sentences(text_to)
        add_sentences(paragraph, sens)

        # Since we're adding sentences to a place where they already exist, we
        # need to update their numbers by the number of the sentence being
        # appended to.
        #
        # NOTE: This does not account for updating numbers of sentences
        # appearing after the newly added sentences. That must be done by the
        # mechanism that applies this file to the existing law.
        for node in paragraph.xpath("sen"):
            node.attrib["nr"] = str(int(node.attrib["nr"]) + int(action_node.attrib["nr"]))
            inner.append(node)

        del paragraph

    else:
        raise IntentParsingException("Don't know how to add sentence to tag: %s" % existing.tag)

    tracker.intents.append(E(
        "intent",
        {
            "action": "append",
            "action-xpath": action_xpath,
        },
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        inner,
    ))

    return True


def parse_vid_x_laganna_baetist_nyr_staflidur_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_vid_x_laganna_baetist_nyr_tolulidur_svohljodandi
    match = re.match(r"Við (.+) laganna bætist nýr stafliður, svohljóðandi: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("add", address, "numart")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["subart", "numart"]:
        base_numart = existing[0].xpath("//numart")[-1]
        numart = construct_node(base_numart, text_to)
        inner.append(numart)
    else:
        raise IntentParsingException("Don't know how to add numart (alphabetic) at address: %s" % address)

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_vid_x_laganna_baetist_nyr_tolulidur_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with:
    #     parse_vid_x_laganna_baetist_nyr_staflidur_svohljodandi
    match = re.match(r"Við (.+) laganna bætist nýr töluliður, svohljóðandi: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()

    intent = tracker.make_intent("add", address, "numart")
    existing = deepcopy(list(intent.find("existing")))

    inner = E("inner")
    if len(existing) == 1 and existing[0].tag in ["subart", "numart"]:
        base_numart = existing[0].xpath("//numart")[-1]
        numart = construct_node(base_numart, text_to)
        inner.append(numart)
    else:
        raise IntentParsingException("Don't know how to add numart (numeric) at address: %s" % address)

    intent.append(inner)
    tracker.intents.append(intent)

    return True


def parse_log_thessi_taka_gildi_d_m_y___(tracker: IntentTracker):
    match = re.match(r"Lög þessi taka gildi (%s)( .*)?" % ICELANDIC_DATE_REGEX, tracker.current_text)
    if match is None:
        return False

    raw_date, _, _, _, raw_extra = match.groups()
    timing = dateparser.parse(raw_date)
    extra = "" if raw_extra is None else raw_extra.strip()

    intent = E(
        "intent",
        {
            "action": "enact",
            "action-xpath": "",
            "action-timing": timing.strftime("%Y-%m-%d"),
        },
    )
    if extra:
        intent.attrib["action-extra"] = extra

    tracker.intents.append(intent)

    return True


def parse_log_thessi_odlast_gildi_d_m_y___(tracker: IntentTracker):
    match = re.match(r"Lög þessi öðlast gildi (%s)( .*)?" % ICELANDIC_DATE_REGEX, tracker.current_text)
    if match is None:
        return False

    raw_date, _, _, _, raw_extra = match.groups()
    timing = dateparser.parse(raw_date)
    extra = "" if raw_extra is None else raw_extra.strip()

    intent = E(
        "intent",
        {
            "action": "enact",
            "action-xpath": "",
            "action-timing": timing.strftime("%Y-%m-%d"),
        },
    )
    if extra:
        intent.attrib["action-extra"] = extra

    tracker.intents.append(intent)

    return True


def parse_log_thessi_odlast_thegar_gildi___(tracker: IntentTracker):
    # In this case, we'll be working with the text itself and no sub-content.
    text = tracker.current_text
    if not text.startswith("Lög þessi öðlast þegar gildi"):
        return False

    timing = "undetermined"
    implemented_timing = ""
    if text == "Lög þessi öðlast þegar gildi.":
        timing = "immediate"
    elif text.startswith("Lög þessi öðlast þegar gildi og koma til framkvæmda"):
        timing = "immediate-with-delayed-implementation"
        implemented_timing = text[52:]  # By length of conditional string above.
    elif text.startswith("Lög þessi öðlast þegar gildi og skulu koma til framkvæmda"):
        timing = implemented_timing = text[58:].strip(".")

    # FIXME: Both `timing` and `implemented_timing` are either magic strings or
    # copied verbatum from the data. They should both be parsed into ISO-8601
    # format here. Note that actual values might be retrieved from metadata.

    # NOTE: This seems pointless, but is here to illustrate how things must
    # probably be done when we run into enactment clauses that don't enact the
    # entire law in one go. It is possible that certain clauses get enacted
    # before others, or that they don't take effect until later. The following
    # lines serve as a building block for such functionality.
    existing = tracker.get_existing("/law")
    action_xpath = make_xpath_from_node(existing)  # Currently always "".

    intent = E(
        "intent",
        {
            "action": "enact",
            "action-xpath": action_xpath,
            "action-timing": timing,
        },
    )
    if implemented_timing:
        intent.append(E("implemented-timing", implemented_timing))

    tracker.intents.append(intent)

    return True


def parse_intents_by_text_analysis(advert_tracker: AdvertTracker, original: _Element) -> bool:

    tracker = IntentTracker(original)

    current_text = tracker.current_text

    if parse_tafla_i_x_laganna_ordast_svo(tracker):
        pass
    elif parse_x_laganna_ordast_svo(tracker):
        pass
    elif parse_x_i_logunum_ordast_svo(tracker):
        pass
    elif parse_eftirfarandi_breytingar_verda_a_x_laganna(tracker):
        pass
    elif parse_vid_x_laganna_baetist_nyr_malslidur_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetast_tveir_nyir_malslidir_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_ny_grein_x_asamt_fyrirsogn_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_ny_grein_x_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_ny_malsgrein_svohljodandi(tracker):
        pass
    elif parse_vid_login_baetast_tvö_ny_akvaedi_til_bradabirgda_svohljodandi(tracker):
        pass
    elif parse_akvaedi_til_bradabirgda_x_i_logunum_fellur_brott(tracker):
        pass
    elif parse_ordin_x_i_x_laganna_falla_brott(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_nyr_malslidur_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist_nyr_staflidur_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist_nyr_tolulidur_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_koma_tvaer_nyjar_greinar_x_og_x_svohljodandi(tracker):
        pass
    elif parse_a_eftir_tilvisuninni_x_i_x_laganna_kemur(tracker):
        pass
    elif parse_a_eftir_ordunum_x_i_x_laganna_kemur(tracker):
        pass
    elif parse_a_eftir_ordinu_x_i_x_laganna_kemur(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_nyr_tolulidur_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist(tracker):
        pass
    elif parse_i_stad_x_laganna_kemur_einn_nyr_malslidur_svohljodandi(tracker):
        pass
    elif parse_i_stad_ordanna_x_i_x_laganna_kemur(tracker):
        pass
    elif parse_i_stad_ordsins_x_i_x_laganna_kemur(tracker):
        pass
    elif parse_i_stad_ordsins_x_tvivegis_i_x_laganna_kemur(tracker):
        pass
    elif parse_i_stad_hlutfallstolunnar_x_og_artalsins_x_tvivegis_i_x_i_logunum_kemur(tracker):
        pass
    elif parse_i_stad_fjarhaedarinnar_x_i_x_laganna_kemur(tracker):
        pass
    elif parse_i_stad_tilvisunarinnar_x_i_x_laganna_kemur(tracker):
        pass
    elif parse_vid_login_baetist_ny_grein_svohljodandi(tracker):
        pass
    elif parse_vid_login_baetist_ny_grein_x_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetast_tvaer_nyjar_malsgreinar_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetast_thrjar_nyjar_malsgreinar_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist_ny_malsgrein_svohljodandi(tracker):
        pass
    elif parse_vid_x_i_logunum_baetist_ny_malsgrein_svohljodandi(tracker):
        pass
    elif parse_a_undan_x_laganna_kemur_ny_grein_x_svohljodandi(tracker):
        pass
    elif parse_log_thessi_odlast_thegar_gildi___(tracker):
        pass
    elif parse_log_thessi_taka_gildi_d_m_y___(tracker):
        pass
    elif parse_log_thessi_odlast_gildi_d_m_y___(tracker):
        pass
    elif parse_x_laganna_fellur_brott(tracker):
        pass
    elif parse_x_i_logunum_falla_brott(tracker):
        pass
    elif parse_x_laganna_falla_brott(tracker):
        pass
    else:
        raise IntentParsingException("Can't figure out: %s" % current_text)

    advert_tracker.targets.art.append(tracker.intents)

    return True
