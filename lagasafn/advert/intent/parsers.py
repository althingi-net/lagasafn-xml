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
import json
import re
from lagasafn.advert.tracker import AdvertTracker
from lagasafn.advert.intent.tracker import IntentTracker
from lagasafn.exceptions import IntentParsingException
from lagasafn.models.intent import IntentModelList
from lagasafn.utils import get_all_text
from lagasafn.utils import Matcher
from lagasafn.utils import super_iter
from lagasafn.utils import write_xml
from lxml.builder import E
from lxml.etree import _Element
from openai import OpenAI
from typing import List


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
    match = re.match(r"(.+) laganna orðast svo:", tracker.peek_text)
    if match is None:
        return False

    address = match.groups()[0]

    next(tracker.lines)
    remaining = tracker.lines.remaining()

    if len(remaining) != 1:
        raise IntentParsingException("Unimplemented: Replacement with multiple lines.")

    text_to = get_all_text(remaining[0])

    tracker.intents.append(E(
        "intent",
        E("action", "replace"),
        E("address", address),
        E("text-to", text_to),
    ))

    return True


def parse_a_eftir_x_laganna_kemur_ny_malsgrein_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á eftir (.+) laganna kemur ný málsgrein, svohljóðandi", tracker.peek_text)
    if match is None:
        return False

    address = match.groups()[0]

    next(tracker.lines)
    remaining = tracker.lines.remaining()

    if len(remaining) != 1:
        raise IntentParsingException("Don't know what to do with non-singular addition of subart.")

    text_to = get_all_text(remaining[0])

    tracker.intents.append(E(
        "intent",
        E("action", "add_subart"),
        E("address", address),
        E("text-to", text_to),
    ))

    return True


def parse_sub_vid_x_baetist(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við (.+) bætist: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()

    tracker.intents.append(E(
        "intent",
        E("action", "add_text"),
        E("address", address),
        E("text-to", text_to),
    ))

    return True


def parse_sub_x_falla_brott(tracker: IntentTracker, li: _Element):
    match = re.match(r"(.+) falla brott\.", get_all_text(li))
    if match is None:
        return False

    address = match.groups()[0]

    tracker.intents.append(E(
        "intent",
        E("action", "delete"),
        E("address", address),
    ))

    return True


def parse_sub_vid_x_baetast_x_nyir_malslidir_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við (.+) bætast (.+) nýir málsliðir, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address = match.groups()[0]
    text_to = match.groups()[2]

    tracker.intents.append(E(
        "intent",
        E("action", "add_sens"),
        E("address", address),
        E("text-to", text_to),  # Must be separated programmatically, possibly asking user.
    ))

    return True


def parse_sub_vid_x_baetist_nyr_malslidur_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við (.+) bætist nýr málsliður, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()

    tracker.intents.append(E(
        "intent",
        E("action", "add_sen"),
        E("address", address),
        E("text-to", text_to),
    ))

    return True


def parse_sub_vid_baetist_ny_malsgrein_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við bætist ný málsgrein, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    text_to = match.groups()[0]

    # NOTE: The address isn't specified here. It will be in the parent node.
    tracker.intents.append(E(
        "intent",
        E("action", "add_paragraph"),
        E("text-to", text_to),
    ))

    return True


def parse_sub_vid_baetist_nyr_tolulidur_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við bætist nýr töluliður, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    text_to = match.groups()[0]

    # NOTE: The address isn't specified here. It will be in the parent node.
    tracker.intents.append(E(
        "intent",
        E("action", "add_numart_numeric"),
        E("text-to", text_to),
    ))

    return True


def parse_sub_x_ordast_svo(tracker: IntentTracker, li: _Element):
    match = re.match(r"(.+) orðast svo: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()

    tracker.intents.append(E(
        "intent",
        E("action", "replace"),
        E("address", address),
        E("text-to", text_to),
    ))

    return True


def parse_eftirfarandi_breytingar_verda_a_x_laganna(tracker: IntentTracker):
    # NOTE: That questionable space at the end happens occurs in advert 45/2024.
    match = re.match(r"Eftirfarandi breytingar verða á (.+) laganna ?:", tracker.peek_text)
    if match is None:
        return False

    address = match.groups()[0]
    tracker.intents.attrib["common-address"] = address

    next(tracker.lines)
    remaining = tracker.lines.remaining()

    if len(remaining) != 1:
        raise IntentParsingException("Don't know what to do with more than one numart.")

    ol = remaining[0]
    if ol.tag != "ol":
        raise IntentParsingException("Unexpected tag for numart.")

    for li in ol.findall("li"):
        li_text = get_all_text(li)

        if parse_sub_vid_x_baetist(tracker, li):
            pass
        elif parse_sub_x_falla_brott(tracker, li):
            pass
        elif parse_sub_vid_x_baetast_x_nyir_malslidir_svohljodandi(tracker, li):
            pass
        elif parse_sub_vid_x_baetist_nyr_malslidur_svohljodandi(tracker, li):
            pass
        elif parse_sub_vid_baetist_ny_malsgrein_svohljodandi(tracker, li):
            pass
        elif parse_sub_vid_baetist_nyr_tolulidur_svohljodandi(tracker, li):
            pass
        elif parse_sub_x_ordast_svo(tracker, li):
            pass
        else:
            raise IntentParsingException("Can't figure out list text: %s" % li_text)

    return True


def parse_vid_x_laganna_baetist_nyr_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Við (.+) laganna bætist nýr málsliður, svohljóðandi: (.+)", tracker.peek_text)
    if match is None:
        return False

    address, text_to = match.groups()

    tracker.intents.append(E(
        "intent",
        E("action", "add_sen"),
        E("address", address),
        E("text-to", text_to),
    ))

    return True


def parse_a_eftir_x_laganna_kemur_ny_grein_x_asamt_fyrirsogn_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á eftir (.+) laganna kemur ný grein, (.+), ásamt fyrirsögn, svohljóðandi:", tracker.peek_text)
    if match is None:
        return False

    address, art_nr_new = match.groups()

    tracker.intents.append(E(
        "intent",
        E("action", "add_art"),
        E("address", address),
        E("art-nr-new", art_nr_new),
        E("art-content", "[unimplemented]"),
    ))

    return True


def parse_vid_login_baetast_x_ny_akvaedi_til_bradabirgda_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Við lögin bætast (.+) ný ákvæði til bráðabirgða, svohljóðandi:", tracker.peek_text)
    if match is None:
        return False

    tracker.intents.append(E(
        "intent",
        E("action", "add_temporary_clauses"),
        E("art-content", "[unimplemented]"),
    ))

    return True


def parse_a_eftir_x_laganna_kemur_nyr_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á eftir (.+) laganna kemur nýr málsliður, svohljóðandi: (.+)", tracker.peek_text)
    if match is None:
        return False

    address, text_to = match.groups()

    tracker.intents.append(E(
        "intent",
        E("action", "add_sen"),
        E("address", address),
        E("text-to", text_to),
    ))

    return True


def parse_vid_x_laganna_baetist_nyr_staflidur_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Við (.+) laganna bætist nýr stafliður, svohljóðandi: (.+)", tracker.peek_text)
    if match is None:
        return False

    address, text_to = match.groups()

    tracker.intents.append(E(
        "intent",
        E("action", "add_numart_alphabetic"),
        E("address", address),
        E("text-to", text_to),
    ))

    return True


def parse_enactment_timing(tracker: IntentTracker):
    # In this case, we'll be working with the text itself and no sub-content.
    text = tracker.peek_text
    if not text.startswith("Lög þessi öðlast þegar gildi"):
        return False

    next(tracker.lines)

    timing = "undetermined"
    implemented_timing = ""
    if text == "Lög þessi öðlast þegar gildi.":
        timing = "immediate"
    elif text.startswith("Lög þessi öðlast þegar gildi og koma til framkvæmda"):
        timing = "immediate-with-delayed-implementation"
        implemented_timing = text[52:]  # By length of conditional string above.

    intent = E(
        "intent",
        E("action", "enact"),
        E("timing", timing),
    )
    if implemented_timing:
        intent.append(E("implemented-timing", implemented_timing))

    tracker.intents.append(intent)

    return True


def parse_intents_by_text_analysis(advert_tracker: AdvertTracker, original: _Element) -> bool:

    tracker = IntentTracker(original)

    peek_text = tracker.peek_text

    if parse_x_laganna_ordast_svo(tracker):
        pass
    elif parse_eftirfarandi_breytingar_verda_a_x_laganna(tracker):
        pass
    elif parse_vid_x_laganna_baetist_nyr_malslidur_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_ny_grein_x_asamt_fyrirsogn_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_ny_malsgrein_svohljodandi(tracker):
        pass
    elif parse_vid_login_baetast_x_ny_akvaedi_til_bradabirgda_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_nyr_malslidur_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist_nyr_staflidur_svohljodandi(tracker):
        pass
    elif parse_enactment_timing(tracker):
        pass
    else:
        raise IntentParsingException("Can't figure out: %s" % peek_text)

    advert_tracker.targets.art.append(tracker.intents)

    return True
