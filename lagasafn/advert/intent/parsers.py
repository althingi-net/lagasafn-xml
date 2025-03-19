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
from copy import deepcopy
import json
import re
from lagasafn.advert.tracker import AdvertTracker
from lagasafn.advert.intent.tracker import IntentTracker
from lagasafn.contenthandlers import add_sentences
from lagasafn.contenthandlers import analyze_art_name
from lagasafn.contenthandlers import separate_sentences
from lagasafn.exceptions import IntentParsingException
from lagasafn.models.intent import IntentModelList
from lagasafn.references import parse_reference_string
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
    match = re.match(r"(.+) laganna orðast svo:", tracker.current_text)
    if match is None:
        return False

    next(tracker.lines)

    address = match.groups()[0]
    existing, xpath = tracker.get_existing_from_address(address)

    inner = E("inner")
    tracker.targets.inner = inner

    tracker.intents.append(E(
        "intent",
        E("action", "replace"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        tracker.targets.inner,
    ))

    prefilled = {
        "nr": existing.attrib["nr"],
    }
    if existing.tag == "art":
        # The function `parse_inner_art` won't be able to determine the type of
        # content, except as determined by `prefilled`. It relies on us only
        # calling it when we know that we expect an article.
        #
        # We know that it's an article at this point, but we'd like
        # `parse_inner_art` to pick up the subarticle inside the article, so we
        # back up by one step here to make sure that the `subart` gets caught.
        tracker.lines.index -= 1

        prefilled["nr_title"] = existing.find("nr-title").text

        parse_inner_art(tracker, prefilled)
    elif existing.tag == "subart":
        parse_inner_art_subart(tracker, prefilled)
    else:
        raise IntentParsingException("Unimplemented tag type for this context: %s" % existing.tag)

    tracker.targets.inner = None

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
    if tracker.lines.current.tag != "ol":
        return False

    # Figure out the number type.
    nr_type = ""
    if tracker.lines.current.attrib["style"] == "list-style-type: lower-alpha;":
        nr_type = "alphabet"
    else:
        raise IntentParsingException("Unsupported numart nr-type (as of yet).")

    lis = tracker.lines.current.findall("li")
    for i, li in enumerate(lis):
        # Just to distinguish between a number that starts at 0 (the `for`
        # loop) and the number we'll be using for generating data.
        seq = i + 1

        # Determine the `nr` that will belong to the `numart`. In the adverts,
        # the content relies on browser rendering of CSS styles to render this
        # to the user, instead of literal text.
        nr = ""
        if nr_type == "alphabet":
            nr = chr(ord("a") - 1 + seq)
        else:
            nr = str(seq)

        numart = E("numart", { "nr": nr, "nr-type": nr_type })

        add_sentences(numart, separate_sentences(li.text))

        tracker.inner_targets.subart.append(numart)

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


def parse_inner_art_address(tracker: IntentTracker, only_check: bool = False):
    if "style" in tracker.lines.current.attrib:
        return False
    match = re.match(r"\((.+)\)", tracker.lines.current.text.strip())
    if match is None:
        return False

    # We may want to only check for the criteria without actually parsing, in
    # which case we exit immediately.
    if only_check:
        return True

    art_nr_title = match.groups()[0]

    art_nr, roman_art_nr = analyze_art_name(art_nr_title)
    if len(roman_art_nr) > 0:
        # We may need to support this, but not until we need to.
        raise IntentParsingException("Unimplemented: Roman numerals not yet implemented for article creation.")

    tracker.inner_targets.art.attrib["nr"] = art_nr
    tracker.inner_targets.art.find("nr-title").text = art_nr_title

    return True


def parse_inner_art(tracker: IntentTracker, prefilled: dict = {}):

    # NOTE: This may actually remain empty and be figured out during parsing of
    # `tracker.lines` later, depending on the nature of the content.
    nr_title = ""
    nr = ""

    # Respect `prefilled["nr_title"]`.
    if "nr_title" in prefilled:
        nr_title = prefilled["nr_title"]

        # Remember, these may both be empty strings if `nr_title` is still
        # empty at this point.
        nr, roman_nr = analyze_art_name(nr_title)

        # Not doing this right away, but we still want to notice it, so that we can do that, once we run into it.
        if len(roman_nr) > 0:
            raise IntentParsingException("Unimplemented: Roman numerals not yet implemented for article creation.")

    # Respect `prefilled["nr"]`.
    if "nr" in prefilled:
        nr = prefilled["nr"]

    # Start making article.
    tracker.inner_targets.art = E("art", { "nr": nr })
    tracker.inner_targets.art.append(E("nr-title", nr_title))

    for line in tracker.lines:
        # If we run into an article address when we already have one, we should
        # start a new article.
        if len(tracker.inner_targets.art.attrib["nr"]) > 0 and parse_inner_art_address(tracker, only_check=True):
            # Take back the attempt to parse this thing, so that the calling
            # function can.
            tracker.lines.index -= 1
            break

        if parse_inner_art_address(tracker):
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

    # Make the intent.
    tracker.intents.append(E(
        "intent",
        E("action", "append_subart"),
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


def parse_vid_x_laganna_baetist_ny_malsgrein_svohljodandi(tracker: IntentTracker):
    # TODO: Excellent candidate for merging with:
    #     parse_a_eftir_x_laganna_kemur_ny_malsgrein_svohljodandi
    match = re.match(r"Við (.+) laganna bætist ný málsgrein, svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    address = match.groups()[0]
    existing, xpath = tracker.get_existing_from_address(address)

    # Make the inner.
    tracker.targets.inner = E("inner")

    # Make the intent.
    tracker.intents.append(E(
        "intent",
        E("action", "add_subart"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        tracker.targets.inner,
    ))

    nr = len(existing.findall("subart"))
    for line in tracker.lines:
        nr += 1
        parse_inner_art_subart(tracker, {"nr": nr })

    tracker.targets.inner = None

    return True


def parse_sub_vid_x_baetist(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við (.+) bætist: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()
    address = "%s %s" % (address, tracker.intents.attrib["common-address"])
    existing, xpath = tracker.get_existing_from_address(address)

    tracker.intents.append(E(
        "intent",
        E("action", "add_text"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("text-to", text_to),
    ))

    return True


def parse_sub_x_falla_brott(tracker: IntentTracker, li: _Element):
    match = re.match(r"(.+) falla brott\.", get_all_text(li))
    if match is None:
        return False

    address = match.groups()[0]
    address = "%s %s" % (address, tracker.intents.attrib["common-address"])
    existing, xpath = tracker.get_existing_from_address(address)

    tracker.intents.append(E(
        "intent",
        E("action", "delete"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
    ))

    return True


def parse_sub_vid_x_baetast_tveir_nyir_malslidir_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við (.+) bætast tveir nýir málsliðir, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()
    address = "%s %s" % (address, tracker.intents.attrib["common-address"])
    existing, xpath = tracker.get_existing_from_address(address)

    tracker.intents.append(E(
        "intent",
        E("action", "add_sens"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("text-to", text_to),  # Must be separated programmatically, possibly asking user.
    ))

    return True


def parse_sub_vid_x_baetist_nyr_malslidur_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við (.+) bætist nýr málsliður, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()
    address = "%s %s" % (address, tracker.intents.attrib["common-address"])
    existing, xpath = tracker.get_existing_from_address(address)

    tracker.intents.append(E(
        "intent",
        E("action", "add_sen"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("text-to", text_to),
    ))

    return True


def parse_sub_vid_baetist_nyr_malslidur_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við bætist nýr málsliður, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    text_to = match.groups()[0]
    address = tracker.intents.attrib["common-address"]
    existing, xpath = tracker.get_existing_from_address(address)

    # NOTE: The address isn't specified here. It will be in the parent node.
    tracker.intents.append(E(
        "intent",
        E("action", "add_sen"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("text-to", text_to),
    ))

    return True


def parse_sub_vid_baetist_ny_malsgrein_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við bætist ný málsgrein, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    text_to = match.groups()[0]
    address = tracker.intents.attrib["common-address"]
    existing, xpath = tracker.get_existing_from_address(address)

    # NOTE: The address isn't specified here. It will be in the parent node.
    tracker.intents.append(E(
        "intent",
        E("action", "add_paragraph"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("text-to", text_to),
    ))

    return True


def parse_sub_vid_baetist_nyr_tolulidur_svohljodandi(tracker: IntentTracker, li: _Element):
    match = re.match(r"Við bætist nýr töluliður, svohljóðandi: (.+)", get_all_text(li))
    if match is None:
        return False

    text_to = match.groups()[0]
    address = tracker.intents.attrib["common-address"]
    existing, xpath = tracker.get_existing_from_address(address)

    tracker.intents.append(E(
        "intent",
        E("action", "add_numart_numeric"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("text-to", text_to),
    ))

    return True


def parse_sub_fyrirsogn_greinarinnar_ordast_svo(tracker: IntentTracker, li: _Element):
    match = re.match(r"Fyrirsögn greinarinnar orðast svo: (.+)", get_all_text(li))
    if match is None:
        return False

    name_new = match.groups()[0]
    address = tracker.intents.attrib["common-address"]
    existing, xpath = tracker.get_existing_from_address(address)

    tracker.intents.append(E(
        "intent",
        E("action", "rename_art"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("text-to", name_new),
    ))

    return True


def parse_sub_x_ordast_svo(tracker: IntentTracker, li: _Element):
    match = re.match(r"(.+) orðast svo: (.+)", get_all_text(li))
    if match is None:
        return False

    address, text_to = match.groups()
    address = "%s %s" % (address, tracker.intents.attrib["common-address"])
    existing, xpath = tracker.get_existing_from_address(address)

    inner = deepcopy(existing)
    if inner.tag == "numart":
        for paragraph in inner.getchildren():
            inner.remove(paragraph)
        inner.append(add_sentences(inner, separate_sentences(text_to)))
    elif inner.tag == "sen":
        # Just making sure that we notice if we run into this weirdness.
        if len(separate_sentences(text_to)) != 1:
            raise IntentParsingException(
                "Unimplemented: Replacing a single referenced sentence with multiple ones."
            )

        # NOTE: We don't need `separate_sentences` here because a specific
        # sentence is being specified.
        inner.text = text_to
    else:
        raise IntentParsingException("Don't know how to replace content in tag: %s" % inner.tag)

    tracker.intents.append(E(
        "intent",
        E("action", "replace"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("inner", inner),
    ))

    return True


def parse_eftirfarandi_breytingar_verda_a_x_laganna(tracker: IntentTracker):
    # NOTE: That questionable space at the end happens occurs in advert 45/2024.
    match = re.match(r"Eftirfarandi breytingar verða á (.+) laganna ?:", tracker.current_text)
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
        elif parse_sub_vid_x_baetast_tveir_nyir_malslidir_svohljodandi(tracker, li):
            pass
        elif parse_sub_vid_baetist_nyr_malslidur_svohljodandi(tracker, li):
            pass
        elif parse_sub_vid_x_baetist_nyr_malslidur_svohljodandi(tracker, li):
            pass
        elif parse_sub_vid_baetist_ny_malsgrein_svohljodandi(tracker, li):
            pass
        elif parse_sub_vid_baetist_nyr_tolulidur_svohljodandi(tracker, li):
            pass
        elif parse_sub_fyrirsogn_greinarinnar_ordast_svo(tracker, li):
            pass
        elif parse_sub_x_ordast_svo(tracker, li):
            pass
        else:
            raise IntentParsingException("Can't figure out list text: %s" % li_text)

    return True


def parse_vid_x_laganna_baetist_nyr_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Við (.+) laganna bætist nýr málsliður, svohljóðandi: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()
    existing, xpath = tracker.get_existing_from_address(address)

    tracker.intents.append(E(
        "intent",
        E("action", "add_sen"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        E("text-to", text_to),
    ))

    return True


def parse_a_eftir_x_laganna_kemur_ny_grein_x_svohljodandi(tracker: IntentTracker):
    # TODO: Great candidate for merging with identical function:
    #     parse_a_eftir_x_laganna_kemur_ny_grein_x_asamt_fyrirsogn_svohljodandi
    match = re.match(r"Á eftir (.+) laganna kemur ný grein, (.+), svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    address, nr_title_new = match.groups()

    intent = E(
        "intent",
        E("action", "add_art"),
        E("address", address),
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


def parse_a_undan_x_laganna_kemur_ny_grein_x_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á undan (.+) laganna kemur ný grein, (.+), svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    address, nr_title_new = match.groups()

    intent = E(
        "intent",
        E("action", "prepend_art"),
        E("address", address),
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


def parse_a_eftir_x_laganna_kemur_ny_grein_x_asamt_fyrirsogn_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á eftir (.+) laganna kemur ný grein, (.+), ásamt fyrirsögn, svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    address, nr_title_new = match.groups()
    existing, xpath = tracker.get_existing_from_address(address)

    intent = E(
        "intent",
        E("action", "add_art"),
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
    match = re.match(r"Á eftir (.+) laganna koma tvær nýjar greinar, (.+) og (.+), svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    address, art_title_new_1, art_title_new_2 = match.groups()

    intent = E(
        "intent",
        E("action", "add_art"),
        E("address", address),
    )
    tracker.intents.append(intent)

    inner = E("inner")
    intent.append(inner)
    tracker.targets.inner = inner

    parse_inner_art(tracker)
    parse_inner_art(tracker)

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
    nr_new = int(last_art.attrib["nr"]) + 1
    nr_title_new = "%d. gr." % nr_new

    intent = E(
        "intent",
        E("action", "add_art"),
        E("address", address),
    )
    tracker.intents.append(intent)

    inner = E("inner")
    intent.append(inner)
    tracker.targets.inner = inner

    parse_inner_art(tracker, {"nr_title": nr_title_new})

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

    nr_title_new = match.groups()[0]
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
    match = re.match(r"(.+) a$", nr_title_new)
    if match is None:
        raise IntentParsingException("Can't figure out where to place new article.")

    address = match.groups()[0]
    del match

    intent = E(
        "intent",
        E("action", "add_art"),
        E("address", address),
    )
    tracker.intents.append(intent)

    inner = E("inner")
    intent.append(inner)
    tracker.targets.inner = inner

    parse_inner_art(tracker, {"nr_title": nr_title_new})

    tracker.targets.inner = None

    return True


def parse_vid_login_baetast_x_ny_akvaedi_til_bradabirgda_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Við lögin bætast (.+) ný ákvæði til bráðabirgða, svohljóðandi:", tracker.current_text)
    if match is None:
        return False

    tracker.intents.append(E(
        "intent",
        E("action", "add_temporary_clauses"),
        E("art-content", "[unimplemented]"),
    ))

    return True


def parse_a_eftir_x_laganna_kemur_nyr_malslidur_svohljodandi(tracker: IntentTracker):
    match = re.match(r"Á eftir (.+) laganna kemur nýr málsliður, svohljóðandi: (.+)", tracker.current_text)
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
    match = re.match(r"Við (.+) laganna bætist nýr stafliður, svohljóðandi: (.+)", tracker.current_text)
    if match is None:
        return False

    address, text_to = match.groups()
    existing, xpath = tracker.get_existing_from_address(address)

    inner = E("inner")

    intent = E(
        "intent",
        E("action", "add_numart_alphabetic"),
        E("address", {"xpath": xpath }, address),
        E("existing", existing),
        inner,
    )
    tracker.intents.append(intent)

    # Since we already have all the content we can gather in this function,
    # we'll just create the `numart` here instead of calling some special
    # parsing function.
    #
    # IMPORTANT: We are currently assuming that the phrasing of this function
    # indicates that the `numart` is being added to a bunch of `numart`s inside
    # the addressed element, and that the address is **not** a sibling of the
    # added `numart`.
    existing_nr = existing.xpath("//numart[@nr-type='alphabet']")[-1].attrib["nr"]
    nr = chr(ord(existing_nr) + 1)
    numart = E("numart", {"nr": nr, "nr-type": "alphabet" })

    add_sentences(numart, separate_sentences(text_to))

    inner.append(numart)

    return True


def parse_enactment_timing(tracker: IntentTracker):
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

    current_text = tracker.current_text

    if parse_x_laganna_ordast_svo(tracker):
        pass
    elif parse_eftirfarandi_breytingar_verda_a_x_laganna(tracker):
        pass
    elif parse_vid_x_laganna_baetist_nyr_malslidur_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_ny_grein_x_asamt_fyrirsogn_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_ny_grein_x_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_ny_malsgrein_svohljodandi(tracker):
        pass
    elif parse_vid_login_baetast_x_ny_akvaedi_til_bradabirgda_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_kemur_nyr_malslidur_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist_nyr_staflidur_svohljodandi(tracker):
        pass
    elif parse_a_eftir_x_laganna_koma_tvaer_nyjar_greinar_x_og_x_svohljodandi(tracker):
        pass
    elif parse_vid_login_baetist_ny_grein_svohljodandi(tracker):
        pass
    elif parse_vid_login_baetist_ny_grein_x_svohljodandi(tracker):
        pass
    elif parse_vid_x_laganna_baetist_ny_malsgrein_svohljodandi(tracker):
        pass
    elif parse_a_undan_x_laganna_kemur_ny_grein_x_svohljodandi(tracker):
        pass
    elif parse_enactment_timing(tracker):
        pass
    else:
        raise IntentParsingException("Can't figure out: %s" % current_text)

    advert_tracker.targets.art.append(tracker.intents)

    return True
