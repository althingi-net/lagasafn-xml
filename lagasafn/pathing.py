import re
import roman
from lagasafn.constants import XML_FILENAME
from lagasafn.exceptions import NoSuchElementException
from lagasafn.exceptions import NoSuchLawException
from lagasafn.exceptions import ReferenceParsingException
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
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


def make_xpath_from_inner_reference(address: str):

    # FIXME: This function began its life as a relatively simple one.
    # Throughout its evolution it has become increasingly convoluted and
    # contains repeated code that could be generalized. In short, refactoring
    # is in order.
    #
    # Ideas for refactoring:
    #
    # 1. Instead of maintaining `xpath` as a string that is changed by various
    #    sections of the function, a dictionary or even a special object might
    #    be used so that adjusting according to its existing content would be
    #    easier. This might allow us to make more concise XPaths, particularly
    #    when it comes to branching (using XPath unions " | ").
    #
    # 2. Commonly used variables like `word` and `peek` could be streamlined,
    #    also eliminating the need for the weird `last_or_blank` function.
    #
    # 3. A special function for dealing with alpha-components here and there,
    #    instead of repeating similar og identical checks all over.

    # We'll be butchering this, so best work on a copy.
    # NOTE: "Address" is synonymous with "inner reference" in this context. We
    # should be updating mentions of "inner references" to "addresses" at some
    # point. In other word, "inner reference" is deprecated wording.
    inner_reference = address

    # Sometimes the more obscure symbol "–" is used to denote ranges but
    # sometimes a regular minus-sign. We'll just want deal with a minus-sign.
    inner_reference = inner_reference.replace("–", "-")

    # Remove space following a range-symbol (minus-sign) so that components of
    # ranges don't get parsed individually.
    inner_reference = inner_reference.replace("- ", "-")

    # Remove dots because they have no meaning in this context and only get in
    # the way.
    inner_reference = inner_reference.replace(".", "")

    # Replace semantic (although consistent) descriptions with more systemic
    # language for easier parsing.
    inner_reference = re.sub(
        r"inngangsmálslið(ur)?", "1 málsl", inner_reference, flags=re.IGNORECASE
    )

    if inner_reference.lower() == "heiti":
        # Refers to the name of the law. Important to be specified from the XML
        # root, so that it doesn't select names of articles or whatever else.
        return "/law/name"

    # Turn the inner reference into a list that's easier to deal. Note that
    # we're processing it from the end because the order of things in a
    # reference is the exact opposite of the order of an XPath.
    # Example:
    # - Reference: 5. mgr. 2. gr.
    # - XPath:     //art[@nr='2']//subart[@nr='5']
    words = inner_reference.split(" ")

    def last_or_blank(some_list):
        """
        Utility function so that we can do this inline.
        """
        return some_list[-1] if len(some_list) else ""

    def make_range(start, end):
        """
        Takes two `nr` attribute values, such as "a" and "h", and returns a
        list of them with all possible values in between.

        This is done both to remedy XPath 1.0's limitation in selecting ranges,
        and to deal with all sorts of special cases and weirdness in the data.
        """

        try:
            if start.isdigit() and end.isdigit():
                # Start by trying conventional numbers.
                letters = range(int(start), int(end) + 1)
            elif is_roman(start) and is_roman(end):
                # Then try Roman numerals.
                start = roman.fromRoman(start)
                end = roman.fromRoman(end)
                latin_range = range(start, end + 1)
                letters = [roman.toRoman(n) for n in latin_range]
            else:
                # Finally, try letters.
                letters = [chr(c) for c in range(ord(start), ord(end) + 1)]

        except Exception:
            raise ReferenceParsingException(
                "Could not determine range between '%s' and '%s'." % (start, end)
            )

        return letters

    xpath = ""

    # This dictionary contains translations from the actual words used in an
    # inner reference, into tag names used in the XML.
    translations = {
        "gr": "art",
        "tölul": "numart",
        "mgr": "subart",
        "málsl": "sen",
        "kafli": "chapter",
        "kafla": "chapter",
    }

    # Consider a complicated address like this:
    # - 3. málsl. 2. mgr. og 2. málsl. 5. mgr. 156. gr.
    #
    # It refers to elements that are quite separate from each other. It really
    # refers to two separate addresses:
    # - 3. málsl. 2. mgr. 156. gr.
    # - 2. málsl. 5. mgr. 156. gr.
    #
    # For this branching to occur, the `branch_at_tag` variable is filled in
    # the loop below when encountering this scenario. The tag at which the
    # branching should occur (in the above case, "mgr." or `subart` is placed
    # in this variable, and then caught at the beginning of the next iteration
    # of the loop.
    branch_at_tag = ""

    while len(words):

        if len(branch_at_tag) > 0:
            # Branch out the XPath, but avoiding duplicates.
            xpath_list = xpath.split(" | ")

            last_selection = xpath_list[-1]

            branching_tag_location = last_selection.rfind("//" + branch_at_tag)
            if branching_tag_location == -1 and branch_at_tag == "sen":
                # When branching by sentence, there may not be a previous `sen`
                # in the XPath. This typically occurs when the semantic phrase
                # "inngangsmálsliður" is used, or some variation thereof, which
                # has actually been replaced with "1 málsl" when the code
                # reaches this point.
                #
                # Example:
                # - A-stafl. 10. gr. laga nr. 105/2024
                #   https://www.stjornartidindi.is/Advert.aspx?RecordID=807f6e79-d283-491d-ae35-34e729daabd5
                #   Specifically:
                #       inngangsmálslið og 4. tölul. 1. mgr., 2. og 4. mgr. og 1. málsl. 5. mgr. 7. gr.
                branching_tag_location = last_selection.rfind("//")

            new_branch = last_selection[:branching_tag_location].rstrip("/")

            xpath_list.append(new_branch)

            xpath = " | ".join(xpath_list)

            del xpath_list, last_selection, new_branch

            branch_at_tag = ""

        # Initialize.
        ent_separator = "//"  # Default.
        ent_type = ""
        ent_numbers = []
        ent_special = ""  # Particularly strange and unusual conditions.

        word = words.pop().strip(",")

        # Check for an alphabetic component to an address like "3. gr. a",
        # where the "a" is the alphabetic component.
        alpha_component = ""
        if re.match(r"^([a-z])$", word) is not None:
            # Catch it.
            alpha_component = word
            # And move forward. The alpha component will be used later.
            word = words.pop()

        if re.search(r"-lið([ua]r)?$", word):
            ent_type = "*[self::numart or self::art-chapter]"

            nr = word[: word.find("-lið")]
            if nr.isdigit():
                ent_numbers.append(nr)
            else:
                # Case-insensitivity for `numart`s denoted by letter.
                ent_numbers.append(nr.lower())
                ent_numbers.append(nr.upper())

        elif word in translations.keys():
            ent_type = translations[word]

            # Construct the number.
            ent_number = words.pop()
            if len(alpha_component) > 0:
                # Add the alpha component if needed.
                ent_number = ent_number + alpha_component

            ent_numbers.append(ent_number)
            del ent_number

        elif re.match(r"[IVXLCDM]+(-[IVXLCDM]+)?$", word):
            # We have run into a Roman numeral in a strange location. It is
            # probably a temporary clause.

            if len(words) == 0:
                # This happens when given the `inner_reference`:
                # "XXII. kafla, 211. eða 218. gr."
                raise ReferenceParsingException("Unimplemented reference style.")

            ent_type = "art"
            ent_numbers.append(word)

            # If we run into temporary clause designation at this point, we
            # have already dealt with it.
            if (
                re.match(r"ákvæði(s)? til bráðabirgða", " ".join(words[-3:]).lower())
                is not None
            ):
                words.pop()
                words.pop()
                words.pop()

        elif word == "í":
            peek = last_or_blank(words)
            if peek.lower() in ["tafla", "töflu"]:
                word = words.pop()
                ent_type = "table"
            elif peek.endswith("“"):
                # The rest is a string inside the content of what's being
                # referenced, so we know that we're done at this point.
                break
            elif peek == "tvívegis":
                # This typically occurs in bills describing multiple instances
                # of something. It's irrelevant in the context of addressing,
                # so we ignore it per se, but still may need to react to its
                # surrounding content for branching.
                words.pop()

                # Remove a possibly preceding and meaningless "og".
                if last_or_blank(words) == "og":
                    words.pop()

                # NOTE: This clause is identical to the one that checks for
                # `word == "og"`.
                # Check if we need to branch.
                peek = last_or_blank(words).strip(",")
                if re.match(r"[a-z]$", peek) is not None and ent_type == "":
                    branch_at_tag = translations[words[-2]]
                elif peek in translations and translations[peek] != ent_type:
                    branch_at_tag = translations[peek]

                continue

            del peek

        elif re.match(r"lokamálsgrein(ar)?", word.lower()) is not None:
            ent_type = "subart"
            ent_special = "last()"

        elif word.lower() == "fyrirsögn":
            ent_separator = "/"
            ent_type = "name"

        elif " ".join(words) == "skilgreiningu á hugtakinu":
            lookup_definition = word.capitalize() + ":"
            ent_type = "paragraph"
            ent_special = "definitions/definition = '%s'" % lookup_definition

            words.pop()
            words.pop()
            words.pop()

        elif word == "og":
            # FIXME: This comment clause is hard to understand.
            #
            # At this point, we're not concatenating anything anymore, but into
            # separated instances of addresses.
            #
            # NOTE: An "og" will typically be caught below, after this run of
            # `if/elif/else` because it typically concatenates internal
            # addresses. This clause is for when it doesn't.

            # NOTE: This clause is identical to the one that checks for
            # `word == "í"`.
            # Check if we need to branch.
            peek = last_or_blank(words).strip(",")
            if re.match(r"[a-z]$", peek) is not None and ent_type == "":
                branch_at_tag = translations[words[-2]]
            elif peek in translations and translations[peek] != ent_type:
                branch_at_tag = translations[peek]

            # Otherwise move on to the next word.
            continue

        elif (
            word == "bráðabirgða"
            and re.match(r"ákvæði(s)? til", " ".join(words[-2:]).lower()) is not None
        ):
            # Whether it's a single temporary article, or a a chapter of
            # temporary articles, it will have the attribute `nr` as "t".
            #
            # Temporary articles inside a temporary chapter will have Roman
            # numerals, so this won't match those (and shouldn't).
            ent_type = "*"
            ent_numbers.append("t")

            words.pop()
            words.pop()
        elif (
            word == "lögin"
            and (
                match := re.match(
                    r"viðauk[ia] (.+) við",
                    " ".join(words[-3:]),
                    re.IGNORECASE,
                )
            )
            is not None
        ):
            ent_type = "appendix"
            ent_numbers.append(match.groups()[0])

            words.pop()
            words.pop()
            words.pop()

        else:
            # Oh no! We don't know what to do!
            raise ReferenceParsingException(
                "Don't know how to parse word: '%s' - whole string: %s"
                % (word, address)
            )

        # The alpha component should be irrelevant at this point.
        del alpha_component

        # All of these combinatory words result in us looking up all of them,
        # so they are all in effect "or", for our purposes.
        if last_or_blank(words) in ["og", "eða", "og/eða"]:
            words.pop()

            # See comment to where `branch_at_tag` is initialized.
            peek = last_or_blank(words)
            if (
                re.match(r"[a-z]$", peek) is not None
                and words[-2] in translations
                and translations[words[-2]] != ent_type
            ):
                branch_at_tag = translations[words[-2]]
            elif peek in translations:
                branch_at_tag = translations[peek]

            else:
                # Find the word that came after "og", "eða", etc.
                word = words.pop()

                if re.match(r"[a-z]$", word):
                    alpha_component = word

                    # Make sure that we're dealing with the same entity type as
                    # the one being parsed.
                    word = words.pop()
                    if translations[word] != ent_type:
                        raise ReferenceParsingException(
                            "Don't know how to figure out concatenation in: %s"
                            % address
                        )

                    word = words.pop() + alpha_component

                ent_numbers.append(word)

                # Support for things like "8., 9. og 10. málsl."
                # We still need to make sure that it's not the beginning of
                # something else, by matching it against `translations`.
                while (
                    last_or_blank(words).endswith(",")
                    and last_or_blank(words).strip(",") not in translations
                ):
                    peek = last_or_blank(words).strip(",")

                    # Support for branching between "15. gr. a" and "7., 9." in
                    # the following example:
                    #     7. og 8. mgr. 15. gr. a, 7., 9. og 10. mgr. 15. gr. b
                    #
                    # This example can be found in:
                    # - b-stafl. 3. gr. laga nr. 105/2024:
                    #   https://www.stjornartidindi.is/Advert.aspx?RecordID=807f6e79-d283-491d-ae35-34e729daabd5
                    if (
                        re.match(r"[a-z]$", peek) is not None
                        and words[-2] in translations
                        and translations[words[-2]] != ent_type
                    ):
                        branch_at_tag = translations[words[-2]]
                        break

                    word = words.pop().strip(",")
                    ent_numbers.append(word)

                # If we run into temporary clause designation at this point, we
                # have already dealt with it.
                if (
                    re.match(
                        r"ákvæði(s)? til bráðabirgða", " ".join(words[-3:]).lower()
                    )
                    is not None
                ):
                    words.pop()
                    words.pop()
                    words.pop()

            del peek

        # Branch XPath when indicated by a comma.
        # Note that this is a separate mechanism from the one that is dealt
        # with by parsing concatenations such as "og" and "eða" above. The
        # difference is that here we might have something like
        # "8. mgr. 5. gr., 2. mgr. 9. gr.", instead of something like
        # "8. og 2. mgr. 9. gr.".
        if last_or_blank(words).endswith(","):
            peek = last_or_blank(words).strip(",")
            if re.match(r"[a-z]$", peek) is not None and words[-2] in translations:
                # We detect an alpha-component here, but we don't need to do
                # anything with it, it will be caught in the next iteration.
                branch_at_tag = translations[words[-2]]
            elif peek in translations:
                branch_at_tag = translations[peek]
            elif re.match(r"[a-z]$", peek):
                # This happens when we have something like "21. gr. c", and we
                # run into the "c" bit of it. We'll need to take the second
                # last entity to determine at which tag to branch the XPath.
                branch_at_tag = translations[words[-2]]
            else:
                raise ReferenceParsingException(
                    "Don't know how to parse concatenated: %s" % peek
                )
            del peek

        # Assuming something came of this...
        if len(ent_type) > 0:
            # ... construct the XPath bit and add it to the result!

            # Process numbers.
            xpath_numbers = []
            for ent_number in ent_numbers:
                if "-" in ent_number:
                    first, second = ent_number.split("-")

                    # We need to select a range of nodes here.
                    # This is a bit convoluted due to limitations in XPath 1.0,
                    # which we are currently stuck with. Instead we'll have to
                    # figure out all the possibilities that could come between
                    # the first and second numbers we get, and then look for
                    # them all.
                    #
                    # There are at least two other ways of doing this that
                    # we've decided against.
                    #
                    # 1. Apply XPath 2.0, which is currently unavailable in
                    # `lxml` and in general not very well supported anywhere.
                    # That would not only introduce a new XML library here, but
                    # also make assumptions about others using the XPath on
                    # their own systems, or in JavaScript in the front-end.
                    #
                    # 2. Have this mechanism look into the XML files for
                    # direction. We wish to avoid this in order to keep this
                    # functionality decoupled from the actual data. It will
                    # also be much, much slower, and require information about
                    # the specific law to which the inner reference belongs.
                    #
                    # Here's a fun problem, though. When an article gets placed
                    # between two existing ones, its number is usually appended
                    # with a character. For example, if we have articles `27`
                    # and `28`, and a new one is added between them, it will
                    # have the `nr` attribute `27a` (and `nr-title` tag of
                    # "27. gr. a").
                    #
                    # An example of this problem can be seen in the 155 version
                    # of lög nr. 50/1993:
                    #
                    #     http http://localhost:8000/api/law/parse-reference/?reference="27-29. gr. laga nr. 50/1993"
                    #
                    # There are not only articles with the `nr` attributes of
                    # `27`, `28` and `29`, but actually `27`, `27a`, `28` and
                    # `29`. To select for those, we not only select for the
                    # `nr` attribute by the value, but also check for anything
                    # that fulfills these conditions:
                    #
                    # 1. Starts with the value (i.e. "27" in the case above).
                    #
                    # 2. Has the string length plus one, i.e.: `len(str(27)) + 1`.
                    #
                    # 3. Is not a number.
                    #
                    # This should only be true in cases where something
                    # non-numeric has been added to a `nr` attribute that is
                    # otherwise numberic. It's not pretty, but it works, and
                    # it's compatible with XPath 1.0.
                    its = make_range(first, second)

                    parts = []
                    for it in its:
                        parts.append("@nr='%s'" % it)

                        # Check for things like "27a" as described above.
                        if type(it) is int:
                            sub_it_length = len(str(it)) + 1
                            parts.append(
                                "(starts-with(@nr, '%s') and string-length(@nr) = %d and string(number(@nr)) != @nr)"
                                % (
                                    it,
                                    sub_it_length,
                                )
                            )

                    xpath_number = "(%s)" % " or ".join(parts)
                else:
                    # FIXME: This checking for a chapter reflects a mistake in
                    # the current XML format (2025-03-27) which needs to be
                    # addressed at some point. Chapters and temporary clauses
                    # (as articles) are typically denoted in Roman numerals.
                    #
                    # However, the `nr` attribute on `chapter` gets turned into
                    # Arabic numerals during parsing and the Roman numeral
                    # retains as `roman-nr`. This is the opposite to temporary
                    # clauses which will have the Roman numeral in the `nr`
                    # attribute, and the Arabic number in `roman-nr`.
                    #
                    # In the future, the XML format should be modified so that
                    # `nr` always contains the number in the form that's the
                    # most likely to be used when looking up the element. For
                    # both chapters and temporary clauses, that means that they
                    # should be Roman numerals, and the Arabic attribute should
                    # be in `roman-nr`, or perhaps even a more generally named
                    # attribute such as `real-nr`.
                    #
                    # Until that happens, we need to condition this thing by
                    # element type.
                    if ent_type == "chapter" and is_roman(ent_number):
                        ent_number = roman.fromRoman(ent_number)

                    # When multiple articles have been deleted, they are
                    # denoted like "12-14. gr." in the `nr_title`, but as a
                    # comma-separated sequence of known possibilities in the
                    # `nr`. Here we check if the `ent_number` is contained in
                    # such a list, but only for articles.
                    #
                    # NOTE: This may need to be extended to `numart`s,
                    # `chapter`s or other elements that may contain ranges.
                    # There shouldn't really anything be wrong with applying
                    # this logic to all elements, but we're trying to keep
                    # down unnecessary complications in the resulting XPath.
                    #
                    # NOTE: This is currently only supported when `ent_number`
                    # is unitary and not itself a range. It shouldn't be
                    # particularly complicated to implement it, we just don't
                    # believe that we'll need it, at this point.
                    if ent_type == "art":
                        xpath_number = (
                            "contains(concat(',', @nr, ','), ',%s,')" % ent_number
                        )
                    else:
                        xpath_number = "@nr='%s'" % ent_number

                xpath_numbers.append(xpath_number)

            if len(ent_special) > 0:
                xpath_numbers.append(ent_special)

            # Add the next node selection to the xpath string.
            xpath += "%s%s" % (ent_separator, ent_type)
            if len(xpath_numbers) > 0:
                xpath += "[%s]" % " or ".join(xpath_numbers)

    return xpath


def get_segment(law_nr: str, law_year: int, xpath: str):
    # FIXME: This should return XML only, not both XML and text versions. If we
    # want a plaintext version, it should be a different API call. However,
    # we're not using plaintext anywhere at the moment, so it can be removed.
    try:
        xml = etree.parse(
            XML_FILENAME % (CURRENT_PARLIAMENT_VERSION, law_year, law_nr)
        ).getroot()
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
