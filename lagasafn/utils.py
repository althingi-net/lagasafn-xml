import json
import re
import roman
import subprocess
from lagasafn import settings
from lagasafn.constants import STRAYTEXTMAP_FILENAME
from lagasafn.constants import XSD_FILENAME
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lxml import etree
from lxml.etree import _Element
from lxml.etree import XMLSchemaValidateError
from os.path import isfile
from typing import List
from xmlschema import XMLSchema


class UnexpectedClosingBracketException(Exception):
    def __str__(self):
        # We'll try to figure out enough information for the user to be able
        # to locate it in the legal text, so that the problem can be examined,
        # the law manually patched and Parliament notified about the error.

        try:
            node = self.args[0]
        except IndexError:
            return Exception("LegalFormatException expects an argument")

        # Work our way up the node hierarchy to construct a list describing
        # the problem node's lineage.
        trail = [node]
        parent = node.getparent()
        while parent.tag != "law":
            trail.insert(0, parent)
            parent = parent.getparent()

        # Construct the error message shown when the Exception is thrown.
        msg = "Unexpected closing bracket. Location: "
        for i, node in enumerate(trail):
            # Show arrow between parent/child relationships.
            if i > 0:
                msg += " -> "

            # Construct tag description.
            msg += "[%s" % node.tag
            if "nr" in node.attrib:
                msg += ":%s" % node.attrib["nr"]
            msg += "]"

        # Append the actual text containing the problem.
        msg += ', in input text "%s"' % node.text

        return msg


# Returns a list of law_ids sorted first by the year ("2020" in "123/2020") as
# the first key, and the legal number as the second key ("123" in "123/2020").
# Law number typecasted to integer to get canonical order.
def sorted_law(law_ids):

    def sorter(law_id):
        nr = law_id[: law_id.find("/")]
        if nr.isdigit():
            nr = int(nr)
        else:
            nr = 0

        return (
            law_id[law_id.find("/") + 1 :],
            nr,
        )

    return list(reversed(sorted(law_ids, key=sorter)))


def numart_next_nrs(prev_numart):
    """
    Returns a list of expected next numbers from the given prev_numart. For
    example, if the prev_numart's number is "1", then "2" and "1a" are
    expected. If it's "b", then "c" is expected.
    """

    matcher = Matcher()

    prev_numart_nr = prev_numart.attrib["nr"]
    expected_numart_nrs = []
    if prev_numart.attrib["nr-type"] == "numeric":
        if prev_numart_nr.isdigit():
            # If the whole thing is numerical, we may expect either the next
            # numerical number (i.e. a 10 after a 9), or a numart with a
            # numerical and alphabetic component (i.e. 9a following a 9).
            expected_numart_nrs = [
                str(int(prev_numart_nr) + 1),
                str(int(prev_numart_nr)) + "a",
            ]

            # But! We may also expect a tree-like numbering scheme:
            # 1.
            # 1.1
            # 1.1.1
            # 1.1.2
            # 1.2.1
            # 1.2.2
            # ...etc.
            # Since "1." is indistinguishable between the "numeric" and "tree"
            # schemes, we need to expect a "tree" scheme, even though the
            # parser currently thinks that it's "numeric".
            #
            # We limit this expectation to single-digit numbers, though, since
            # these structures are extremely unlikely to even reach 9, let
            # alone above.
            if len(prev_numart_nr) == 1:
                expected_numart_nrs.append("%s.1" % prev_numart_nr)

        elif matcher.check(prev_numart_nr, r"(\d+)-(\d+)"):
            # Numarts may be ranges, (see 145. gr. laga nr. 108/2007), in
            # which case we only need to concern ourselves with the latter
            # number to determine the expected values.

            from_numart_nr, to_numart_nr = matcher.result()

            expected_numart_nrs = [
                str(int(to_numart_nr) + 1),
                str(int(to_numart_nr)) + "a",
            ]

        else:
            # If at this point the whole thing starts with a number but is not
            # entirely a number, it means that the numart is a mixture of both
            # (f.e. 9a). In these cases we'll expect either the next number
            # (10 following 9a) or the same number with the next alphabetic
            # character (9b following 9a).
            alpha_component = prev_numart_nr.strip("0123456789")
            num_component = int(prev_numart_nr.replace(alpha_component, ""))

            expected_numart_nrs = [
                str(num_component + 1),
                str(num_component) + chr(int(ord(alpha_component)) + 1),
            ]

    elif prev_numart.attrib["nr-type"] == "tree":
        # NOTE: This could be generalized to support more permutations of
        # predictable `numart_nr`s, but we haven't run across them yet, and
        # these are exceedingly rare, basically only existing in appendices and
        # strange documents. So we'll just let this do until we need something
        # more sophisticated.

        values = prev_numart.attrib["nr"].split(".")

        # Predict that the tree branches out again.
        expected_numart_nrs.append(prev_numart.attrib["nr"] + ".1")

        # Go through each place and figure out what can be expected from any of
        # them being incremented.
        for place, value in enumerate(values):
            dealing_with = values[:place+1]
            expected_numart_nrs.append(
                ".".join(dealing_with[:-1] + [str(int(dealing_with[-1])+1)])
            )

            # A tree-scheme `numart` list may look like this:
            # 1
            # 1.1
            # 1.2
            # 2
            # 2.1
            # 2.2
            # ...etc.
            #
            # But it may also look like this:
            # 1.1
            # 1.2
            # 2.1
            # 2.2
            # ...etc.
            #
            # In other words, "1.2" in the above example must not only expect
            # the next `numart` to include "2", but also "2.1.".
            #
            # If we're handling the second-last place, we'll add another copy
            # of what was created above, except with ".1" appended to it.
            if place == len(values) - 2:
                expected_numart_nrs.append(
                    expected_numart_nrs[-1] + ".1"
                )

    elif prev_numart.attrib["nr-type"] == "en-dash":
        expected_numart_nrs += ["—", "–"]
    elif prev_numart.attrib["nr-type"] == "roman":
        new_roman = roman.toRoman(roman.fromRoman(prev_numart_nr.upper()) + 1)
        if prev_numart_nr.islower():
            new_roman = new_roman.lower()

        expected_numart_nrs.append(new_roman)
    else:
        # Check if an alphabetic numart is surrounded by "(" and ")". Only
        # known to happen in 19/1996, which seems to be, in fact, an
        # international agreement and not a law.
        if prev_numart_nr[0] == "(" and prev_numart_nr[-1] == ")":
            numart_to_increment = prev_numart_nr[1:-1]
            next_numart_nr = "(%s)" % chr(int(ord(numart_to_increment)) + 1)
            expected_numart_nrs.append(next_numart_nr)

        elif prev_numart_nr == "z":
            expected_numart_nrs = ["þ", "aa"]
        elif prev_numart_nr == "þ":
            expected_numart_nrs = "æ"
        elif prev_numart_nr == "æ":
            expected_numart_nrs = "ö"
        elif prev_numart_nr == "ö":
            expected_numart_nrs = ["aa"]
        elif prev_numart_nr == "aa":
            expected_numart_nrs = ["ab", "bb"]
        elif prev_numart_nr == "bb":
            expected_numart_nrs = ["bc", "cc"]
        elif prev_numart_nr == "cc":
            expected_numart_nrs = ["cd", "dd"]
        elif prev_numart_nr == "dd":
            expected_numart_nrs = ["de", "ee"]
        elif prev_numart_nr == "ee":
            expected_numart_nrs = ["ef", "ff"]
        elif prev_numart_nr == "ff":
            expected_numart_nrs = ["fg", "gg"]
        elif prev_numart_nr == "gg":
            expected_numart_nrs = ["gh", "hh"]
        elif prev_numart_nr == "hh":
            expected_numart_nrs = ["hi", "ii"]
        elif prev_numart_nr == "ii":
            expected_numart_nrs = ["ij", "jj"]
        elif prev_numart_nr == "jj":
            expected_numart_nrs = ["jk", "kk"]
        elif prev_numart_nr == "kk":
            expected_numart_nrs = ["kl", "ll"]
        elif prev_numart_nr == "ll":
            expected_numart_nrs = ["lm", "mm"]
        elif prev_numart_nr == "mm":
            expected_numart_nrs = ["mn", "nn"]
        elif prev_numart_nr == "U":
            expected_numart_nrs = ["Ú"]
        elif prev_numart_nr == "Ú":
            expected_numart_nrs = ["V"]
        elif prev_numart_nr == "Z":
            expected_numart_nrs = ["AA"]
        elif prev_numart_nr == "AA":
            expected_numart_nrs = ["AB", "BB"]
        elif prev_numart_nr == "BB":
            expected_numart_nrs = ["BC", "CC"]
        elif prev_numart_nr == "CC":
            expected_numart_nrs = ["CD", "DD"]
        elif prev_numart_nr == "DD":
            expected_numart_nrs = ["DE", "EE"]
        elif prev_numart_nr == "EE":
            expected_numart_nrs = ["EF", "FF"]

        else:
            # If the numart is a range like "a-d", typical for places where
            # multiple numarts have been deleted, the latter part is what we
            # go by, since we'll want to expect the next character afterward.
            #
            # NOTE: This won't work if the range includes any of the crazy
            # situations above, like "bb" or "þ". In order to support those
            # in a range like this, some refactoring is warranted. This check
            # will have to be placed further above, but we're not doing that
            # immediately because it's more complicated than what's needed
            # for now.
            if "–" in prev_numart_nr:
                prev_numart_nr = prev_numart_nr[prev_numart_nr.find("–") + 1 :]
            elif "-" in prev_numart_nr:
                prev_numart_nr = prev_numart_nr[prev_numart_nr.find("-") + 1 :]

            expected_numart_nrs.append(chr(int(ord(prev_numart_nr)) + 1))

    return expected_numart_nrs


def determine_month(month_string):
    """
    Takes a human-readable, Icelandic month name and returns its corresponding
    number in the year. January ("janúar") is 1 and December ("desember") is
    12. The reason for hand-rolling this function instead of using something
    built in Python is because we expect inconsistencies somewhere in the
    legal codex, if not spelling errors then different traditions for
    designating them at different times.

    Another, perhaps more arguable reason, is that we don't want to mix
    assumed localization with the content that we are processing. The content
    will never be in any other locale than Icelandic except in the
    circumstance of an historical exception, in which case Python's handling
    of locale will be a problem, and not a solution. In other words, this is
    mapping of data and not a localization issue.

    Last but not least, this is simply much simpler than doing this through
    locale libraries, both in terms of readability and performance.
    """

    # We know of one instance where the year gets re-added at the end, in
    # version 148c. We'll deal with this by replacing that known string with
    # the month's name only. When the data gets fixed, this line can be
    # removed, but will still be harmless. -2019-01-02
    # String: 2003 nr. 7 11. febrúar 2003
    # UR: https://www.althingi.is/lagas/nuna/2003007.html
    month_string = month_string.replace("febrúar 2003", "febrúar")

    months = [
        "janúar",
        "febrúar",
        "mars",
        "apríl",
        "maí",
        "júní",
        "júlí",
        "ágúst",
        "september",
        "október",
        "nóvember",
        "desember",
    ]

    return months.index(month_string) + 1


def is_roman(goo: str):

    # The `roman` library accepts lowercase Roman numerals, but we may run into
    # alphabetic text that coinciced with Roman numerals, in which case we deem
    # them non-Roman.
    #
    # Note that this makes us responsible for making potentially Roman numerals
    # uppercase if we wish to check if they are indeed Roman numerals.
    if goo.islower():
        return False

    try:
        roman.fromRoman(goo)
        result = True
    except roman.InvalidRomanNumeralError:
        result = False

    return result


def terminal_width_and_height():
    height, width = [int(v) for v in subprocess.check_output(["stty", "size"]).split()]
    return width, height


def strip_links(text, strip_hellip_link=False):
    """
    Strips links from text. Also strips trailing whitespace after the link,
    because there is always a newline and a tab after the links in our input.
    """

    # Start by eliminating space from between the end of a link and symbols
    # that should never have a space before them after a link. These occur
    # because during the cleaning process, HTML code gets placed in its own
    # line and the following symbols in a new line, producing white-space.
    regex = r"(>)\s*([,\.])"
    text = re.sub(regex, r"\1\2", text)

    # There is an occasional link that we would like to preserve. So far, they
    # can identified by their content containing the special character "…",
    # which means that the link is in fact a comment. Instead of stripping
    # these from the HTML, we'll leave them alone and post-process them into
    # proper XML in the main processing function. Note that for the time
    # being, they are left as HTML-encoded text and not actual XML (until the
    # aforementioned XML post-processing takes place).
    #
    # An exception to this occurs in I. viðauki laga nr. 36/2011. In that case,
    # the hellip is actually a deletion marker, which then doesn't get parsed
    # as one, because it contains a link. This is believed to be very rare.
    if strip_hellip_link:
        regex = r"<a [^>]*?>\s*(.*?)\s*</a>"
    else:
        regex = r"<a [^>]*?>\s*([^…]*?)\s*</a>"
    text = re.sub(regex, r"\1", text)

    return text


def xml_lists_identical(one, two):
    """
    Takes two lists of XML nodes and checks whether they have the same
    tagnames, texts (values) and attributes. Does not check subnodes.
    """

    if type(one) is not list or type(two) is not list:
        raise TypeError("xml_lists_identical takes exactly two lists")

    if len(one) != len(two):
        return False

    for i, node in enumerate(one):
        if two[i].tag != node.tag:
            return False
        if two[i].text != node.text:
            return False
        if two[i].attrib != node.attrib:
            return False

    return True


def generate_url(input_node):
    """
    Takes an XML node and returns its URL, or the closest thing we have.
    There is a certain limit to how precise we want to make the URL, both
    because it's not necessarily useful for the user to go deeper than into
    the relevant article, but also because with numarts and such, the anchors
    in the HTML tend to become both unreliable and unpredictable.
    """
    article_nr = None

    node = input_node
    while node.tag != "law":
        if node.tag == "art":
            # If the article is denoted in Roman numerals, it will be upper-case in the URL.
            article_nr = node.attrib["nr"].upper()

        node = node.getparent()

    #########################################################
    # At this point, `node` will be the top-most `law` tag. #
    #########################################################

    # Make sure that the law number is always exactly three digits.
    law_nr = str(node.attrib["nr"])
    while len(law_nr) < 3:
        law_nr = "0%s" % law_nr

    url = "https://www.althingi.is/lagas/%s/%s%s.html#G%s" % (
        settings.CURRENT_PARLIAMENT_VERSION,
        node.attrib["year"],
        law_nr,
        article_nr,
    )

    return url


def generate_legal_reference(input_node, skip_law=False, force_inner_paragraph=False):
    """
    Takes an XML node and returns a string representing the formal way of
    referring to the same location in the legal codex.
    """
    result = ""
    node = input_node
    matcher = Matcher()

    # If we're given the top-most node, which refers to the law itself, then
    # we'll return the legal reference to the law itself (in the nominative
    # case), regardless of whether `skip_law` was true or not, since
    # otherwise we return nothing and that's not useful.
    if node.tag == "law":
        return "lög nr. %s/%s" % (node.attrib["nr"], node.attrib["year"])    

    while node.tag != "law":
        # A few tags are part of the law definition; we don't want to handle it specially
        if node.tag in ["name", "date", "num-and-date", "nr-title", "sen", "footnote-sen", 
                        "footnote", "footnotes", "location", "date", "num", "original", 
                        "minister-clause", "ambiguous-section", "ambiguous-bold-text", "sen-title",
                        "table", "tr", "td", "th", "thead", "tbody"]:
            node = node.getparent()
            continue

        if node.getparent().tag == "footnote":
            node = node.getparent()
            continue

        if node.tag == "numart":
            if node.attrib["nr-type"] == "alphabet":
                result += "%s-stafl. " % node.attrib["nr"]
            elif node.attrib["nr-type"] in ["numeric", "roman", "tree"]:
                result += "%s. tölul. " % node.attrib["nr"]
            elif node.attrib["nr-type"] == "en-dash":
                result += "%s. pkt. " % node.attrib["nr"]
            else:
                raise Exception("Parsing of node not implemented")
        elif node.tag == "art-chapter":
            # Nominative case if first in line, otherwise genitive.
            if not result:
                result += "%s-liður " % node.attrib["nr"]
            else:
                result += "%s-liðar " % node.attrib["nr"]
        elif node.tag == "subart":
            result += "%s. málsgr. " % node.attrib["nr"]
        elif node.tag == "art":
            if node.attrib["nr"].isdigit() or node.attrib["nr"].isnumeric():
                result += "%s. gr. " % node.attrib["nr"]
            else:
                if matcher.check(node.attrib["nr"], r"(\d+)(.+)"):
                    matches = matcher.result()
                    result += "%s. gr. %s " % (matches[0], matches[1])
                elif node.attrib["nr"] == "t":
                    result += "ákvæði til bráðabirgða"
                elif (
                    "number-type" in node.attrib
                    and node.attrib["number-type"] == "roman"
                ):
                    # Roman numerals for article numbers usually indicates that
                    # it's in a chapter of temporary clauses.
                    if node.getparent().attrib["nr"] == "t":
                        # TODO/FIXME: This is not entirely according to norms
                        # and needs to be examined more closely.
                        result += "ákvæði til bráðabirgða %s " % node.attrib["nr"]
                    else:
                        # But maybe not always.
                        result += "%s. gr. " % node.attrib["nr"]
                elif node.getparent().tag == "chapter" and node.getparent().attrib["nr"] == "t":
                    result += "ákvæði til bráðabirgða %s " % node.attrib["nr"]                    
                else:
                    raise Exception("Parsing of node '%s' (xpath %s) not implemented" % (node.tag, node.getroottree().getpath(node)))
        elif node.tag == "paragraph":
            # This is a bit out of the ordinary. This type of paragraphs is
            # typically not denoted in references.
            #
            # They are denoted, basically, when there are more than one
            # paragraph inside a node that typically only contains one
            # paragraph. For example, a paragraph may come after a list of
            # `numart`s, or there indeed be more than one `paragraph` inside a
            # `numart`. Only in those cases do we wish to denote `paragraph`s
            # as "málsgr."
            #
            # However, on occasion we need them to properly place content
            # coming after `numart`s, and of course they are needed
            # under-the-hood to pinpoint locations in the XML. For this reason,
            # the optional boolean parameter `force_inner_paragraph` to force
            # the showing of them, but then they are called "undirmálsgrein"
            # for a clear distinction.
            #
            # Also note that when they are referenced in text, they are just
            # called "málsgr." for Icelandic "málsgreinar". We make the
            # technical distinction between a `subart` and `paragraph`, but in
            # human speech, they are called the same thing ("málsgrein").
            if len(node.getparent().findall("paragraph")) > 1:
                result += "%s. málsgr. " % node.attrib["nr"]
            elif force_inner_paragraph:
                result += "[%s. undirmálsgr.] " % node.attrib["nr"]

        elif node.tag == "appendix-part":
            pass
        elif node.tag == "appendix":
            if "nr-type" not in node.attrib:
                result += "viðauka "
            elif node.attrib["nr-type"] == "arabic":
                result += "%s. viðauka " % node.attrib["nr"]
            elif node.attrib["nr-type"] == "roman":
                result += "%s. viðauka " % node.attrib["roman-nr"]
            else:
                raise Exception("Parsing of node not implemented")
        elif node.tag == "chapter":
            pass
        elif node.tag == "subchapter":
            pass
        elif node.tag == "numart-chapter":
            pass
        elif node.tag == "superchapter":
            pass
        else:
            raise Exception("Parsing of node '%s' not implemented" % node.tag)

        node = node.getparent()

    #########################################################
    # At this point, `node` will be the top-most `law` tag. #
    #########################################################

    # Add the reference to the law unless skipped.
    if not skip_law:
        result += "laga nr. %s/%s" % (node.attrib["nr"], node.attrib["year"])
    else:
        # FIXME: When `skip_law` is `True`, the result will end up with a
        # trailing white-space. We should `strip()` that white-space here.
        #
        # However, the current JSON-map data was made assuming these
        # white-spaces, so if they are stripped here, that data must be
        # re-made, which is a bit of manual labor.
        #
        # There are two ways to fix this:
        #
        # 1. Uncomment the following line and do the manual labor again.
        #
        # 2. Go through the JSON-map files programmatically and strip the
        #    relevant keys.
        #
        # Until either is done, the following line remains commented but
        # retained for future generations to deal with.

        #result = result.strip()
        pass

    return result


# We are given some extra sentences, that we don't know where to locate
# because it cannot be determined by the input text alone.
def ask_user_about_location(extra_sens, numart):
    legal_reference = generate_legal_reference(numart, skip_law=True, force_inner_paragraph=True)
    url = generate_url(numart)

    # Calculated values that we'll have to use more than once.
    joined_extra_sens = " ".join(extra_sens)
    numart_xpath = numart.getroottree().getpath(numart)
    law = numart.getroottree().getroot()

    # Open the straytext map.
    with open(STRAYTEXTMAP_FILENAME % CURRENT_PARLIAMENT_VERSION, "r") as f:
        straytextmap = json.load(f)

    # Construct the straytext map key. It must be quite detailed because we
    # may have multiple instances of the same text, even in the same document.
    straytextmap_key = "%s/%s:%s:%s" % (
        law.attrib["nr"],
        law.attrib["year"],
        numart_xpath,
        joined_extra_sens,
    )

    # Check if the straytext map already has our answer.
    if (
        "--rebuild-straytextmap" not in settings.options
        and straytextmap_key in straytextmap
    ):
        # Okay, we have an entry for this text.
        entry = straytextmap[straytextmap_key]

        # Check if the purported XPath destination fits with the legal
        # reference. If so, we can be confident that the location is correct,
        # even if the law has changed somewhat. This will break if the text
        # gets moved about, but then the user will simply be asked again.
        destination_node = law.xpath(entry["xpath"])[0]
        if (
            generate_legal_reference(destination_node, skip_law=True, force_inner_paragraph=True)
            == entry["legal_reference"]
        ):
            return destination_node

    # Figure out the possible locations to which the text might belong.
    possible_locations = []
    node = numart
    while node.getparent().tag != "law":
        possible_locations.append(node)
        node = node.getparent()

    # Add the law itself as a possible location. Extremely rare, but happens
    # for example in "forsetaúrskurður" nr. 105/2020
    # (https://www.althingi.is/lagas/151c/2020105.html).
    possible_locations.append(law)

    # Try to explain the situation to the user.
    width, height = terminal_width_and_height()
    print()
    print("-" * width)
    print(
        "We have discovered the following text that we are unable to programmatically locate in the XML in:"
    )
    print()
    print("Law: %s/%s" % (law.attrib["nr"], law.attrib["year"]))
    print()
    print("It can be found in: %s" % legal_reference)
    print("Link: %s" % url)
    print()
    print("The text in question is:")
    print()
    print('"%s"' % joined_extra_sens)
    print()
    print(
        "Please open the legal codex in the relevant location, and examine which legal reference is the containing element of this text."
    )
    print()
    print("The options are:")
    for i, possible_location in enumerate(possible_locations):
        print(" - %d: %s" % (i + 1, generate_legal_reference(possible_location, force_inner_paragraph=True)))
    print()
    print(" - 0: Skip (use only when answer cannot be provided)")

    # Get the user to decide.
    response = None
    while response not in range(0, len(possible_locations) + 1):
        try:
            response = int(input("Select appropriate option: "))
        except ValueError:
            # Ignore nonsensical answer and keep asking.
            pass

    # User opted to skip this one.
    if response == 0:
        return None

    # Determine the selected node and get its reference.
    selected_node = possible_locations[response - 1]
    selected_node_legal_reference = generate_legal_reference(
        selected_node, skip_law=True, force_inner_paragraph=True
    )

    # Tell the user what they selected.
    print("Selected location: %s" % selected_node_legal_reference)

    # Write this down in our straytextmap for later consultation, using the
    # sentences as a key to location information.
    straytextmap[straytextmap_key] = {
        "xpath": selected_node.getroottree().getpath(selected_node),
        "legal_reference": selected_node_legal_reference,
    }
    with open(STRAYTEXTMAP_FILENAME % CURRENT_PARLIAMENT_VERSION, "w") as f:
        json.dump(straytextmap, f)

    return selected_node


# A super-iterator for containing all sorts of extra functionality that we
# don't get with a regular Python iterator. Note that this thing is
# incompatible with yields and is NOT a subclass of `iter` (since that's not
# possible), but rather a class trying its best to masquerade as one.
class super_iter:
    def __init__(self, collection):
        self.collection = collection
        self.index = -1

    def __next__(self):
        self.index += 1
        try:
            result = self.collection[self.index]
        except IndexError:
            # Prevent index from growing beyond length.
            self.index = len(self.collection)
            raise StopIteration
        return result

    def prev(self):
        self.index -= 1
        if self.index < 0:
            # Prevent index from shrinking below -1.
            self.index = -1
            raise StopIteration
        return self.collection[self.index]

    def __len__(self):
        return len(self.collection)

    def __iter__(self):
        return self
    
    @property
    def current(self):
        if self.index < 0:
            return None
        if self.index >= len(self.collection):
            return None
        return self.collection[self.index]

    # Peek into the next item of the iterator without advancing it. Works with
    # negative numbers to take a peek at previous items.
    def peek(self, number_of_places=1):
        peek_index = self.index + number_of_places
        if peek_index >= len(self.collection) or peek_index < 0:
            return None
        return self.collection[peek_index]

    def peeks(self, number_of_places=1):
        r = self.peek(number_of_places)
        if r:
            return r.strip()
        return None


class Matcher:
    """
    A helper class to be able to check if a regex matches in an if-statement,
    but then process the results in its body, if there's a match. This is
    essentially to make up for Python's (consciously decided) inability to
    assign values to variables inside if-statements. Note that a single
    instance of it is created and then used repeatedly.

    Usage:

    if matcher.check(line, '<tag goo="(\\d+)" splah="(\\d+)">'):  # noqa
        goo, splah = matcher.result()
    """

    match = None

    def check(self, line, test_string):
        self.match = re.match(test_string, line)
        return self.match is not None

    def result(self):
        return self.match.groups()


class Trail:
    """
    A helper class for keeping track of what has been added lately to the XML
    being processed at any given point in time. Used to determine the context
    of what is currently being processed.

    Currently, we only ever need the last node added, so strictly speaking
    this could just remember one node at a time, but it's quite conceivable
    that we'll need to be able to look them up further back for additional
    context. For this reason, we keep the history of nodes added.

    Usage:

        if Trail.last().tag == 'art':
            Trail.last().append(some_thing)
    """

    def __init__(self):
        self.milestones = []
        self.nodes = []

    def set_milestone(self, milestone):
        """
        May be used to set a milestone that can then be checked to see later
        if it has been reached. For example, 'intro-finished' is a milestone
        that tells us whether we have finished the intro or not.
        """
        self.milestones.append(milestone)

    def milestone_reached(self, milestone):
        """
        Check to see if the provided milestone has been reached.
        """
        return milestone in self.milestones

    def append(self, appended_node):
        """
        Appends a given node to the trail.
        """

        self.nodes.append(appended_node)

    def last(self):
        """
        Gets the last node appended.
        """

        return self.nodes[-1]


def validate_xml(xml_doc) -> bool:
    """
    Validates the given XML document if an XSD exists.

    Returns `True` if validation took place and was successful.
    Returns `False` if there is no corresponding XSD schema.
    Raises exceptions when validation fails.
    """
    if not isfile(XSD_FILENAME % xml_doc.tag):
        return False

    schema = XMLSchema(XSD_FILENAME % xml_doc.tag)
    schema.validate(xml_doc)

    return True


def write_xml(xml_doc, filename=None, skip_strip=False):
    # FIXME: The `skip_strip` parameter convolutes things and possibly
    # unnecessarily. It is only used in one instance, to write the remote
    # advert HTML. This remote advert HTML then gets converted into XML. To
    # remove the `skip_strip` parameter, the conversion from remote advert HTML
    # to advert XML should work even when `skip_strip=False`.

    # Strip all elements in document by default.
    # This can be side-stepped because certain data gets screwed up by it.
    if not skip_strip:
        for element in xml_doc.iter():
            # If the element has text, strip leading and trailing whitespace.
            if element.text:
                element.text = element.text.strip()

            # If the element has tail, strip leading and trailing whitespace.
            if element.tail:
                element.tail = element.tail.strip()

    validate_xml(xml_doc)

    etree.indent(xml_doc, level=0)
    xml_string = etree.tostring(
        xml_doc, pretty_print=True, xml_declaration=True, encoding="utf-8"
    ).decode("utf-8")

    # The "<" symbol gets escaped as "&lt;" earlier in the process, but the
    # `etree.tostring` function above re-escapes it to `&amp;lt;". We'll
    # un-escape it here, instead of dealing with CDATA encapsulation or the
    # like.
    xml_string = xml_string.replace("&amp;lt;", "&lt;")

    if filename is not None:
        with open(filename, "w") as f:
            f.write(
                xml_string
            )

    return xml_string


def traditionalize_law_nr(law_nr: str) -> str:
    """
    Takes a law number as input and returns a string that represents Althingi's
    traditional way of expressing it in a filename or for sorting.

    Example: 77/2021 becomes: 2021077.html

    Laws from before 1885 are sequenced by date instead of an incrementing
    number, so they are dealt with differently.
    """
    result = str(law_nr)

    if result[0] == "m":
        # Deal with pre-1885 law numbers, which were dates instead of
        # sequential numbers.
        #
        # The logic here is not obvious. The 3-digit number is created from the
        # date, but in quite an unusual way.
        #
        # The first two digits are the day of month. Reasonable enough.
        # The last digit is the latter digit of the month, excluding the first
        # digit of the month. So if the month is "12", the last digit is "2".
        #
        # This is bizarre but doesn't really matter because it only applies to
        # historical data and there aren't any clashes in it, and laws have
        # been sequenced by an incrementing integer since at least 1885.
        #
        # Examples:
        #       3 12    123
        #       | ||    |||
        #     m07d02 -> 027
        #     m04d15 -> 154
        #     m10d28 -> 280
        first_two = result[-2:]
        third = result[2]

        result = "%s%s" % (first_two, third)
    else:
        while len(result) < 3:
            result = "0%s" % result

    return result


def untraditionalize_law_nr(law_nr: str, law_year: int) -> str:
    """
    Does the reverse of what `traditionalize_law_nr` does, i.e. takes a
    pre-1885 law number as it is defined by Althingi, and turns it into the
    filename format that we prefer.
    """
    weird_month = law_nr[-1]
    if weird_month == "0":
        # Happens in m10d28/1828, where zero means 10. This strange naming
        # scheme will never be used again, so we just hard-code it here.
        weird_month = "10"
    elif len(weird_month) == 1:
        weird_month = "0%s" % weird_month

    weird_day = law_nr[0:-1]
    if len(weird_day) == 1:
        weird_day = "0%s" % weird_day
    elif law_nr == "0":
        # Happens in m07d00/1764 and m00d00/1275, where there is no day
        # specified. Hard-coded here since this will never be done again and
        # only applies to these very particular, ancient data.
        if law_year == 1764:
            weird_day = "00"
            weird_month = "07"
        elif law_year == 1275:
            weird_day = "00"
            weird_month = "00"

    untraditionalized = "m%sd%s" % (weird_month, weird_day)
    return untraditionalized


def last_container_added(input_node):
    """
    Finds the last container node added to the `input_node`.

    These are found by finding the last node in the document, excluding
    `nr-title` and `name`.
    """
    children = input_node.xpath("*[not(self::nr-title or self::name)]")
    if len(children) == 0:
        return input_node
    else:
        return last_container_added(children[-1])


def find_unmatched_closing_bracket(content):
    """
    Finds the next closing marker in a string, that doesn't have a
    corresponding opening marker before it.

    We may need to find the closing marker "]" in a text that contains other
    opening and closing markers, for example in "one [two] three] four" we'll
    want to find the one by "three" instead of the one by "two", because the
    one at "two" matches the opening marker before it.
    """

    opening_count = 0

    for index, char in enumerate(content):
        if char == "[":
            opening_count += 1
        elif char == "]":
            if opening_count > 0:
                opening_count -= 1
            else:
                return index
    return -1


def search_xml_doc(xml_doc, search_string):
    """
    Finds nodes in a list of lxml XML document objects that contain the specified search string in their content.

    :param xml_docs: A list of lxml.etree.ElementTree objects, each representing an XML document.
    :param search_string: The string to search for in the content of XML nodes.
    :return: A list of nodes that contain the search string in their text content from all documents.
    """
    matching_nodes = []

    for element in xml_doc.iter():
        if element.text and search_string.lower() in element.text.lower():
            matching_nodes.append(element)

    return matching_nodes


def find_common_ancestor(node_1, node_2):
    """
    Finds the common ancestor of two XML nodes.
    """
    ancestors = set()
    while node_1 is not None:
        ancestors.add(node_1)
        node_1 = node_1.getparent()

    while node_2 is not None:
        if node_2 in ancestors:
            return node_2
        node_2 = node_2.getparent()

    return None


def regex_find(string_value, regex, start=0):
    """
    A replication of the `.find` function on strings, that supports the `start`
    parameter, except that it finds by regex.

    :param content: The text to search within.
    :param regex: The regex pattern to match.
    :param cursor: The position to start the search from.
    :return: The position of the first match if found, otherwise -1.
    """
    match = re.search(regex, string_value[start:])
    return start + match.start() if match else -1


def convert_to_text(elements: List[_Element]):
    """
    FIXME: Should be consolidated with `get_all_text` function below.
    """
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

    return result.strip()


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

    result = remove_garbage(result)

    return result


def remove_garbage(input_string: str):
    """
    Removes garbage like non-breaking space, soft-hyphens, double spaces and
    such, which tends to be in the original data, but only makes things more
    difficult in all sorts of different ways.
    """
    # Remove non-breaking space.
    result = input_string.replace("\xa0", " ")

    # Remove soft-hyphen.
    result = result.replace("\u00AD", "")

    # Consolidate spaces.
    while result.find("  ") > -1:
        result = result.replace("  ", " ")

    # Strip the result.
    result = result.strip()

    return result


def number_sorter(number):
    """
    Used for properly sorting numbers in a string, so that "7" comes before
    "70" by prepending zeroes.
    """
    result = str(number)
    while len(result) < 3:
        result = "0%s" % result
    return result
