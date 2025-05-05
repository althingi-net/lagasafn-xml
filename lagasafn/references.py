import re
from lagasafn.constants import XML_FILENAME
from lagasafn.constants import XML_INDEX_FILENAME
from lagasafn.constants import XML_REFERENCES_FILENAME
from lagasafn.contenthandlers import strip_markers
from lagasafn.exceptions import NoSuchLawException
from lagasafn.exceptions import ReferenceParsingException
from lagasafn.multiprocessing import CustomPool
from lagasafn.pathing import get_segment
from lagasafn.pathing import make_xpath_from_node
from lagasafn.pathing import make_xpath_from_inner_reference
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.utils import number_sorter
from lagasafn.utils import strip_links
from lagasafn.utils import untraditionalize_law_nr
from lagasafn.utils import write_xml
from lxml import etree
from lxml.builder import E
from os.path import isfile

# Words that we can use to conclusively show that we are at the end of parsing
# the inner part of a reference.
# IMPORTANT: These should not be confusable with the end of a law's name.
conclusives = [
    "af",
    "að",
    "annars",
    "auglýsingaskyldu",
    "á",
    "ákvæða",
    "ákvæði",
    "ákvæðis",
    "ákvæðum",
    "ásamt",
    "brott",
    "einnig",
    "ef",
    "eftir",
    "eldri",
    "er til",  # Important; must not be "til" because that has inner-reference meaning.
    "framar",
    "framkvæmd",
    "fylgja",
    "fyrir",
    "fyrirmælum",
    "gegn",
    "gilda",
    "gildi",
    "gildir",
    "gildistíð",
    "gildistöku",
    "grundvelli",
    "gæta",
    "heimild",
    "fjárhæðir",
    "í",
    "ívilnunarúrræðum",
    "kröfur",
    "leyti",
    "lögum",
    "þessara laga",
    "málsmeðferðarreglna",
    "með",
    "með síðari breytingum",
    "meðal annars",
    "né",
    "núgildandi",
    "reglum",
    "reglur",
    # "ríkisútvarpið" occurs only in 23/2013. The string is actually "gilda um
    # Ríkisútvarpið", which could also be remedied by turning `conclusives`
    # into regexes and allowing some text after "gilda um". Seeing that it
    # won't fix any other problem than this exact line, we'll just leave the
    # name "ríkisútvarpið" here instead for now and possibly forever.
    "ríkisútvarpið",
    "samkvæmt",
    "samnefndum",
    "samræmast",
    "sbr.",
    "sbr. nú",
    "setja",
    "setningar",
    "skal",
    "skilgreiningu",
    "skilningi",
    "skilyrði",
    "skilyrðum",
    "skulu",
    "skv.",
    "stað",
    "svo og",
    "tilliti til",  # Important; must not be "til" because that has inner-reference meaning.
    "tíð",
    "undanþegin",
    "undanþegnar",
    "undir",
    "utan",
    "við",
    "vísan til",
    # NOTE: "þessara" will be used to find legal references as well (for
    # example "1. gr. laga þessara") but here they are used to determine the
    # conclusive end of the parsing of an inner reference.
    "þessara",
    "þessi",
    "þessum",
    "þó",
    "öðru leyti til",
]

# Patterns describing node-delimited parts of inner references.
# IMPORTANT: The entire things must be in a group because the length of the
# entire match is needed in code below.
inner_reference_patterns = [
    r"(([A-Z]{1,9}\.?[-–])?([A-Z]{1,9})\. kafl[ia]( [a-zA-Z])?)$",  # `chapter`
    r"(([A-Z]{1,9}\.?[-–])?([A-Z]{1,9})\. hluta( [A-Z])?)$",  # `chapter`-ish
    r"([A-Z][-–]hluta( [A-Z])?)$",  # `chapter`-ish (another version)
    r"(((\d{1,3})\.( gr\.( [a-zA-Z] )?)?[-–] ?)?(\d{1,3})\. gr\.( [a-zA-Z])?(,)?)$",  # `art`
    r"(((\d{1,3})\.[-–] ?)?(\d{1,3})\. mgr\.)$",  # `subart`
    r"(((\d{1,3})\.[-–] ?)?(\d{1,3})\. tölul\.)$",  # `numart`
    r"(([a-zA-Z][-–])?[a-zA-Z][-–]lið(ar)?)$",  # `numart` (alphabetic)
    r"(([a-zA-Z][-–]) til [a-zA-Z][-–]liða)$",  # `numart` (alphabetic)
    r"(((\d{1,3})\.[-–] ?)?(\d{1,3})\. málsl\.)$",  # `sen`
]

# Patterns describing parts that may appear before "og" but don't conform to
# the `inner_reference_patterns` above.
#
# Examples:
#     a- og c–i-lið 9. tölul. 14. og 15. gr.
#     1., 2. eða 5. mgr. 109. gr.
#
# IMPORTANT: The entire things must be in a group because the length of the
# entire match is needed in code below.
and_inner_reference_patterns = [
    r"(((\d{1,3})\.[-–] ?(\d{1,3})\., )*(\d{1,3})\.[-–] ?(\d{1,3})\.)$",
    r"((([A-Za-z])[-–], )*([A-Za-z])[-–])$",
    r"(((\d{1,3})\., )*(\d{1,3})\.)$",
    r"(((([A-Z]{1,9})\.[-–])?([A-Z]{1,9})\., )*(([A-Z]{1,9})\.[-–])?([A-Z]{1,9})\.)$",
]

separators = ["og/eða", "og", "eða"]

# Construct a regex pattern that will exclude what may otherwise appear to
# be references to laws.
# FIXME: There has to be a tidier way to do this.
law_pattern_regex = r"nr\. (\d{1,3}\/\d{4})"
law_pattern_disqualifiers = [
    r"Stjórnartíðindi Evrópusambandsins",
    # Special case for "sameiginlegu EES-nefndarinnar nr. 104/2004 frá 9. júlí
    # 2004 sem birt var 23. desember 2004 í EES-viðbæti við Stjórnartíðindi
    # Evrópusambandsins nr. 65 og nr. 131/2020 frá" in lög nr. 61/2016.
    # NOTE: Regex requires this to be fixed-width, so if we'll need `\d{1,3}`
    # or the like, we may have to have multiple lines for `\d{1}`, `\d{2}` and
    # `\d{3}`. At that point, however, refactoring may a more proper solution.
    r"Stjórnartíðindi Evrópusambandsins nr\. \d{2} og",
    r"EES-nefndarinnar",
    r"EES-nefndarinnar,",
    r"við EES-samninginn",
    r"auglýsingu",
]
for disqualifier in law_pattern_disqualifiers:
    law_pattern_regex = r"(?<!" + disqualifier + " )" + law_pattern_regex

law_permutations = {}

def get_law_name_permutations(codex_version: str = ""):
    """
    Provides a dictionary with law ID as key, containing every known
    permutation of the law's name, such as declensions, as well as synonyms and
    their declensions.
    """

    if codex_version == "":
        codex_version = CURRENT_PARLIAMENT_VERSION

    if len(law_permutations) > 0:
        return law_permutations

    index = etree.parse(XML_INDEX_FILENAME % codex_version).getroot()

    for law_entry in index.xpath("/index/law-entries/law-entry"):
        name_nomenative = law_entry.find("./name-conjugated/accusative").text
        name_accusative = law_entry.find("./name-conjugated/accusative").text
        name_dative = law_entry.find("./name-conjugated/dative").text
        name_genitive = law_entry.find("./name-conjugated/genitive").text
        nr_and_year = "%s/%s" % (law_entry.attrib["nr"], law_entry.attrib["year"])

        # Make sure the law exists before we start filling it with stuff.
        if nr_and_year not in law_permutations:
            law_permutations[nr_and_year] = {}

        # These should always exist.
        law_permutations[nr_and_year]["main"] = {
            "nomenative": name_nomenative,
            "accusative": name_accusative,
            "dative": name_dative,
            "genitive": name_genitive,
        }

        # Add synonyms and their declensions.
        synonyms = law_entry.xpath("./synonyms/synonym")
        if len(synonyms) > 0:
            for number, synonym in enumerate(synonyms):
                law_permutations[nr_and_year]["synonym_%d" % (number + 1)] = {
                    "nomenative": synonym.find("nomenative").text,
                    "accusative": synonym.find("accusative").text,
                    "dative": synonym.find("dative").text,
                    "genitive": synonym.find("genitive").text,
                }

    return law_permutations


def analyze_potentials(potentials):
    # Check for inner parts of reference for as long as we can.
    #
    # FIXME: This `beendone` loop-checking thing is ridiculous. We should
    # remove things from `potentials` until it's empty and break there.

    reference = ""

    # Becomes True if the underlying mechanism is able to conclusively
    # determine that the inner reference has been parsed completely and
    # correctly. This typically happens when we run into key words like "skv."
    # or "sbr.".
    certain_about_inner = False

    loop_found = False

    law_permutations = get_law_name_permutations()
    flat_permutations = []
    for nr in law_permutations:
        for dimension in law_permutations[nr].keys():
            cases = law_permutations[nr][dimension]
            flat_permutations.extend([cases[case] for case in cases.keys()])

    beendone = 0
    while True:

        # Check if we're actually done.
        if potentials == "":
            certain_about_inner = True
            break

        # Check for inner reference parts by iterating through known patterns.
        for inner_pattern in inner_reference_patterns:
            nrs_and_years = re.findall(inner_pattern, potentials)
            if len(nrs_and_years) > 0:
                match = nrs_and_years[0][0]
                if len(reference) and reference[0] == ",":
                    # Avoid space if placing before a comma.
                    reference = "%s%s" % (match, reference)
                else:
                    reference = "%s %s" % (match, reference)
                potentials = potentials[: -len(match)].strip()

                del match
                continue

        # Check for and consume comma.
        if potentials.endswith(","):
            reference = ", %s" % reference
            potentials = potentials[:-1]
            continue

        # Check if we can prove that we're done by using conclusive words.
        for conclusion_part in conclusives:
            p_len = len(potentials)
            cp_len = len(conclusion_part)
            if p_len >= cp_len and potentials[-cp_len:].lower() in conclusives:
                certain_about_inner = True
                break
        if certain_about_inner:
            # Break outer loop as well.
            break

        # Check if we can prove that we're done by seeing if another outer
        # reference can be found right before.
        preceeding_law_match = re.findall(r"(nr\. (\d{1,3}/\d{4}),)$", potentials)
        if len(preceeding_law_match):
            pl_len = len(preceeding_law_match[0][0])
            potentials = potentials[-pl_len:]
            certain_about_inner = True
            break

        # Check for separators "og/eða", "og" and "eða".
        separator = ""
        for sep_try in separators:
            if len(potentials) < len(sep_try):
                continue

            if potentials[-len(sep_try) :] == sep_try:
                separator = sep_try
                break

        # If we can find a permutation of a law name, it means that this
        # current reference is complete. The found permutation will then be
        # detected again as a separate reference in the next round.
        for permutation in flat_permutations:
            permutation = permutation.removeprefix("lögum ")
            if potentials.removesuffix(",").endswith(permutation):
                certain_about_inner = True
                break
        if certain_about_inner:
            # Break outer loop as well.
            break

        if len(separator):
            # If we run into a separator with no inner reference, then this is
            # a reference to the entire law and not to an article within it. We
            # may safely assume that we're done parsing.
            if len(reference) == 0:
                certain_about_inner = True
                break

            # The string ", " preceeding the separator indicates that what
            # comes before is not a part of the same reference. We determine
            # that the reference is complete.
            # FIXME: This is a pretty daring assumption. Probably needs a
            # deeper exploration of what comes before the comma.
            if potentials.rstrip(separator)[-2:] == ", ":
                certain_about_inner = True
                break

            # Otherwise, add matched separator and continue.
            reference = "%s %s" % (separator, reference)
            potentials = potentials[: -len(separator)].strip()

            # Parts before separators (such "og" or "eða") follow a different
            # format, as their context is determined by what comes after them.
            #
            # Consider:
            #     a- og c–i-lið 9. tölul.
            #
            # The "a-" part doesn't make any sense except in the context of
            # "c-i-lið" that comes afterward. We don't normally parse "a-"
            # individually, we only parse it after we run into an "og".
            for and_inner_pattern in and_inner_reference_patterns:
                nrs_and_years = re.findall(and_inner_pattern, potentials)
                if len(nrs_and_years) > 0:
                    match = nrs_and_years[0][0]
                    reference = "%s %s" % (match, reference)
                    potentials = potentials[: -len(match)].strip()
                    del match

                del nrs_and_years

            # We don't need to concern ourselves more with this iteration.
            # Moving on.
            continue

        # If we can't find any more matches, we're out of the inner part of the
        # reference or into something that we don't support yet.
        if beendone > 100:
            loop_found = True
            break
        beendone += 1

    # May contain stray separator.
    for separator in separators:
        reference = reference.removeprefix(separator).strip()

    # May contain stray comma.
    reference = reference.removeprefix(",").strip()

    # May contain stray whitespace due to concatenation.
    reference = reference.strip()

    return reference, certain_about_inner, loop_found


def process_law_references(law_id: str):
    """
    Processes references in a law given by `law_id` into XML.

    Note that it must return a string instead of an XML node, because functions
    used with `multiprocessing.Pool` must be picklable, and an XML node is not.
    """

    law_nr, law_year = law_id.split("/")
    law_year = int(law_year)

    law_filename = XML_FILENAME % (CURRENT_PARLIAMENT_VERSION, law_year, law_nr)
    if not isfile(law_filename):
        # Very old laws have a different filename structure. We'll try that
        # before giving up.
        law_nr = untraditionalize_law_nr(law_nr, law_year)
        law_filename = XML_FILENAME % (CURRENT_PARLIAMENT_VERSION, law_year, law_nr)
        if not isfile(law_filename):
            raise NoSuchLawException(law_filename)

    law_ref_entry = E(
        "law-ref-entry", {"law-nr": str(law_nr), "law-year": str(law_year)}
    )

    law = etree.parse(law_filename).getroot()

    sens = law.xpath("//sen[not(ancestor::footnotes)]")
    for sen in sens:
        # We'll be butchering this so better make a copy.
        chunk = strip_links(sen.text or "")

        nrs_and_years = re.findall(law_pattern_regex, chunk)
        for nr_and_year in nrs_and_years:

            # NOTE: Every law has a name, so if this doesn't exist,
            # `nr_and_year` cannot refer to a law unless there's a mistake
            # in the legal codex itself.
            #
            # TODO: We might want to collect these and figure out if there
            # are any such mistakes, or if we can further utilize these
            # references even if they don't refer to laws.

            # Check if the law being referenced actually exists.
            # NOTE: It is conceivable that something being caught here
            # actually refers to a non-law denoted by the same pattern,
            # such as a regulation or an international document.
            if nr_and_year not in law_permutations:

                # FIXME: Disabled for refactoring. Probably better handled
                # differently, and possibly not at all, since this information
                # has not been actually used for anything so far.
                #problems["does-not-exist"].append(
                #    {
                #        "nr_and_year": nr_and_year,
                #        "sen": sen,
                #    }
                #)
                continue

            # Possible permutations of how the outer part of reference
            # might be construed.
            potential_start_guesses = [
                "l. nr. %s" % nr_and_year,
                "lög nr. %s" % nr_and_year,
                "lögum nr. %s" % nr_and_year,
                "þágildandi laga, nr. %s" % nr_and_year,
                "laga nr. %s" % nr_and_year,
                " lögum, nr. %s" % nr_and_year,
                " laga, nr. %s" % nr_and_year,
                "[law-marker] nr. %s" % nr_and_year,
            ]

            for category in law_permutations[nr_and_year]:
                accusative = law_permutations[nr_and_year][category]["accusative"]
                dative = law_permutations[nr_and_year][category]["dative"]
                genitive = law_permutations[nr_and_year][category]["genitive"]
                potential_start_guesses.extend(
                    [
                        "%s, nr. %s" % (accusative, nr_and_year),
                        "%s, nr. %s" % (dative, nr_and_year),
                        "%s, nr. %s" % (genitive, nr_and_year),
                        "%s nr. %s" % (accusative, nr_and_year),
                        "%s nr. %s" % (dative, nr_and_year),
                        "%s nr. %s" % (genitive, nr_and_year),
                    ]
                )

            # a string holding potential parts of an inner reference. gets
            # continuously analyzed and chipped away at, as we try to
            # include as much as we can.
            potentials = ""

            # begin by finding out where the next outer reference starts.
            def next_outer_reference(chunk, potential_start_guesses):
                # note: we call this a starting location, but we're parsing
                # backwards into the string from the starting location,
                # even though we're looking for the starting location
                # forward.
                potentials_outer_start = -1
                potentials_outer_end = -1

                for potential_start_guess in potential_start_guesses:

                    # we match by lowercase, in case the name of the law
                    # has an uppercase letter, which happens for example
                    # when a sentence begins with it. the location is the
                    # same regardless of case.
                    attempt = chunk.lower().find(potential_start_guess.lower())

                    if potentials_outer_start == -1 or (
                        attempt > -1 and attempt < potentials_outer_start
                    ):
                        potentials_outer_start = attempt

                        # Record the outer end location so that we can
                        # decide where to end the label constructed later.
                        potentials_outer_end = attempt + len(potential_start_guess)

                return potentials_outer_start, potentials_outer_end

            potentials_outer_start, potentials_outer_end = next_outer_reference(
                chunk,
                potential_start_guesses
            )

            # The outer and inner references we will build.
            reference = ""

            certain_about_inner = False
            loop_found = False
            if potentials_outer_start > -1:

                # Potentials are the string that potentially contains the
                # inner parts of a reference, i.e. without the law's number
                # and name.
                potentials = chunk[:potentials_outer_start].strip()

                reference, certain_about_inner, loop_found = analyze_potentials(
                    strip_markers(potentials)
                )

                # FIXME: Disabled for refactoring. Should probably just throw
                # an exception and be handled by the calling function.
                #if loop_found:
                #    stat_loop_count += 1

            # The visible part of the text that would normally be
            # expected to be a link on a web page.
            link_label = ""
            if len(reference) > 0:
                link_label = chunk[
                    chunk.rfind(
                        reference, 0, potentials_outer_end
                    ) : potentials_outer_end
                ]
            else:
                link_label = chunk[potentials_outer_start:potentials_outer_end]

            # Remove the `[law-marker]` from the `link_label`, if we used
            # it to determine that this is a law.
            #
            # Look for `[law-marker]` in the code for details on it.
            link_label = link_label.removeprefix("[law-marker] ")

            # Finally, a link label may contain space because they may be
            # used to indicate the start of a pattern in
            # `potential_start_guesses`.
            link_label = link_label.strip()

            # Generate an XPath to the current node containing the
            # reference.
            location = make_xpath_from_node(sen)

            if certain_about_inner:

                # To adhere to our established norm of separating law
                # number and law year.
                target_law_nr, target_law_year = nr_and_year.split("/")
                target_law_year = int(target_law_year)

                # Either find or construct the node for the given entry.
                ref_node = law_ref_entry.find('node[@location="%s"]' % location)
                if ref_node is None:
                    ref_node = E(
                        "node",
                        {
                            "location": location,
                            "text": strip_links(sen.text or ""),
                        },
                    )
                    law_ref_entry.append(ref_node)

                ref_reference = E(
                    "reference",
                    {
                        "link-label": link_label,
                        "inner-reference": reference,
                        "law-nr": target_law_nr,
                        "law-year": str(target_law_year),
                    },
                )

                if len(reference) == 0:
                    # Formally record this as a success by setting the
                    # `xpath` attribute to an empty string.
                    ref_reference.attrib["xpath"] = ""
                else:
                    try:
                        xpath = make_xpath_from_inner_reference(reference)
                        try:
                            get_segment(target_law_nr, target_law_year, xpath)
                            ref_reference.attrib["xpath"] = xpath
                        except Exception:
                            ref_reference.attrib["xpath-resolution-failure"] = "true"
                        del xpath

                    except ReferenceParsingException:
                        ref_reference.attrib["xpath-failure"] = "true"

                ref_node.append(ref_reference)

                # Since we know that this is a reference, we can cut it out
                # of the chunk, so that it won't be confusing the parser
                # when it finds another reference immediately following it.
                chunk = chunk[potentials_outer_end:].strip()

                # Also remove things that are legitimate inside the
                # reference, so that we don't confuse the parser when it
                # shows up at the beginning of the string.
                chunk = chunk.removeprefix(", ")
                chunk = chunk.removeprefix("og ")
                chunk = chunk.removeprefix("eða ")

                # We were able to determine that this is a reference to a
                # law because the text contained one of the forms listed in
                # `potential_start_guesses`.
                #
                # Sometimes a referenced law is immediately followed by
                # references to other laws, which do not contain enough
                # information to independently determine that they are laws
                # (as opposed to regulations or whatever else).
                #
                # An example can be found in:
                # https://www.althingi.is/lagas/153c/2022006.html
                #
                # > Samninga við önnur ríki og gerð þeirra og framkvæmd
                # > tiltekinna samninga, sbr. meðal annars lög nr. 90/1994,
                # > nr. 57/2000, nr. 93/2008 og nr. 58/2010.
                #
                # To remedy this, we will add a custom law indicator,
                # "[law-marker] ", before them, so they can be picked up
                # by `potential_start_guesses` later. This indicator is
                # then removed from the `link_label` so that it doesn't
                # show up in the final product.
                #
                # Check if what follows is a law without enough information
                # to see it in the parent loop.
                if chunk.find("nr. ") == 0:
                    chunk = "[law-marker] " + chunk

                # This is a good debugging point when you need to take a
                # look at something that works here before it fails in the
                # next iteration.
                #
                # if sen.text.find("Beginning of some `sen.text`...") == 0:
                #     import ipdb; ipdb.set_trace()

            else:
                print()
                print()
                print("### Problem detected ###")
                print("- Processing: %s/%s" % (law_nr, law_year))
                print("- Text:       %s" % sen.text)
                print("- Chunk:      %s" % chunk)
                print("- Potentials: %s" % potentials)
                print("- Law:        %s" % nr_and_year)
                print("- Reference:  %s" % reference)
                print("- Loop: %s" % ("true" if loop_found else "false"))

                # This is a good debugging point.
                #
                # if loop_found:  # For debugging loops.
                #     import ipdb; ipdb.set_trace()
                #
                # import ipdb; ipdb.set_trace()

        # Indent for: `for nr_and_year in matches`
        pass

    return etree.tostring(law_ref_entry)



def parse_references(law_ids):
    print("Parsing references...", end="", flush=True)

    xml_ref_doc = E("references")

    # Every law will have some permutations. Those include declensions
    # (accusative, dative, etc.) and synonyms and also their declensions.
    # This only makes sure that the permutations are cached for the function
    # `process_law_references`, which will need them again and again.
    get_law_name_permutations()

    entries = []

    with CustomPool() as pool:
        results = pool.run(process_law_references, law_ids)

        while True:
            try:
                law_ref_entry_string = next(results)
                law_ref_entry = etree.fromstring(law_ref_entry_string)

                # Finally add the entry to the XML document.
                entries.append(law_ref_entry)

                print(".", end="", flush=True)

            except StopIteration:
                break

    # Sort entries for consistency.
    entries.sort(
        key=lambda e: (
            e.attrib["law-year"],
            number_sorter(e.attrib["law-nr"])
        ),
        reverse=True
    )

    for entry in entries:
        xml_ref_doc.append(entry)

    # Apply statistics to XML.
    xml_ref_doc.attrib["stat-conclusive-count"] = str(len(xml_ref_doc.xpath("//reference")))
    xml_ref_doc.attrib["stat-xpath-successes"] = str(len(xml_ref_doc.xpath("//reference[@xpath]")))
    xml_ref_doc.attrib["stat-xpath-failures"] = str(len(xml_ref_doc.xpath("//reference[@xpath-failure='true']")))
    xml_ref_doc.attrib["stat-xpath-resolution-failures"] = str(len(xml_ref_doc.xpath("//reference[@xpath-resolution-failure='true']")))

    write_xml(xml_ref_doc, XML_REFERENCES_FILENAME % CURRENT_PARLIAMENT_VERSION)

    print(" done")


def parse_reference_string(reference):
    # TODO: Sanity check on reference to prevent garbage input.
    # ...
    # FIXME: This function turns the input `reference` into a list and then
    # does some weird stuff to remove the outer reference (law name and law
    # nr/year). It would be better to strip the nr/year and name by more
    # sophisticated means, as this functionality makes certain assumptions
    # about the relationship between the inner and outer references.

    law_nr = None
    law_year = None

    # Make sure there are no stray spaces in reference. They often appear when
    # copying from PDF documents.
    reference = reference.strip()
    while reference.find("  ") > -1:
        reference = reference.replace("  ", " ")

    # Turn reference into words that we will parse one by one, but backwards,
    # because human-readable addressing has the most precision in the
    # beginning ("1. tölul. 2. gr. laga nr. 123/2000") but data addressing the
    # other way around.
    words = reference.split(" ")
    words.reverse()

    # Parse law number and year if they exist.
    if "/" in words[0] and words[1] == "nr.":
        law_nr, law_year = words[0].split("/")
        law_year = int(law_year)
        words.pop(0)
        words.pop(0)

    # Map of known human-readable separators and their mappings into elements.
    known_seps = {
        "gr.": "art",
    }

    # Look for a known separator, forwarding over the possible name of the law
    # and removing it, since it's not useful. This disregards the law's name.
    known_sep_found = False
    while not known_sep_found:
        if words[0] in known_seps:
            known_sep_found = True
        elif re.match(r"^[a-z]$", words[0]) is not None:
            # Account for things like "52. gr. a".
            known_sep_found = True
        else:
            words.pop(0)
    del known_sep_found

    # At this point the remaining words should begin with something we can
    # process into a location inside a document.

    # Reconstruct the inner references from the list we've been using, without
    # the outer reference.
    words.reverse()
    inner_reference = " ".join(words)
    del words

    # Create XPath selector from inner reference.
    xpath = make_xpath_from_inner_reference(inner_reference)

    return xpath, law_nr, law_year
