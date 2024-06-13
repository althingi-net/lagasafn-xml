import re
from lagasafn.constants import XML_FILENAME
from lagasafn.constants import XML_INDEX_FILENAME
from lagasafn.constants import XML_REFERENCES_FILENAME
from lagasafn.pathing import make_xpath_from_node
from lagasafn.utils import write_xml
from lxml import etree
from lxml.builder import E

# Words that we can use to conclusively show that we are at the end of parsing
# the inner part of a reference.
conclusives = [
    "auglýsingaskyldu",
    "á",
    "ákvæði",
    "ákvæðum",
    "einnig",
    "eftir",
    "fyrir",
    "gegn",
    "gilda",
    "grundvelli",
    "í",
    "með",
    "meðal annars",
    "né",
    "reglum",
    "samkvæmt",
    "samræmast",
    "sbr.",
    "skilningi",
    "skilyrði",
    "skilyrðum",
    "skv.",
    "undanþegnar",
    "undir",
    "við",
]

# Patterns describing node-delimited parts of inner references.
# IMPORTANT: The entire things must be in a group because the length of the
# entire match is needed in code below.
inner_reference_patterns = [
    r"(([A-Z]{1,9}\.?[-–])?([A-Z]{1,9})\. kafla( [A-Z])?)$",  # `chapter`
    r"(([A-Z]{1,9}\.?[-–])?([A-Z]{1,9})\. hluta( [A-Z])?)$",  # `chapter`-ish
    r"(((\d{1,3})\.[-–] ?)?(\d{1,3})\. gr\.( [a-z])?(,)?)$",  # `art`
    r"(((\d{1,3})\.[-–] ?)?(\d{1,3})\. mgr\.)$",  # `subart`
    r"(((\d{1,3})\.[-–] ?)?(\d{1,3})\. tölul\.)$",  # `numart`
    r"(([a-zA-Z][-–])?[a-zA-Z][-–]lið(ar)?)$",  # `numart` (alphabetic)
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
    r"(([A-Za-z])[-–])$",
    r"(((\d{1,3})\., )*(\d{1,3})\.)$",
    r"(([A-Z]{1,9})\.)$",
]


def get_conjugated_law_names(index):
    # First iterate all the law entries to find all dative forms, which we will
    # need in its entirety later, when parsing the law.
    conjugated = {}
    for law_entry in index.xpath("/index/law-entries/law-entry"):
        name_accusative = law_entry.xpath("./name-conjugated/accusative")[0].text
        name_dative = law_entry.xpath("./name-conjugated/dative")[0].text
        name_genitive = law_entry.xpath("./name-conjugated/genitive")[0].text
        nr_and_year = "%s/%s" % (law_entry.attrib["nr"], law_entry.attrib["year"])
        conjugated[nr_and_year] = {
            "accusative": name_accusative,
            "dative": name_dative,
            "genitive": name_genitive,
        }
    return conjugated


def parse_references():
    print("Parsing references...", end="", flush=True)

    # These will record statistics as we run through the data, applied to the
    # XML afterwards.
    stat_loop_count = stat_conclusive_count = stat_inconclusive_count = 0
    xml_ref_doc = E("references")

    index = etree.parse(XML_INDEX_FILENAME).getroot()

    # This keeps track of sentences that we haven't figured out how to deal
    # with yet. We can use them to incrementally improve the reference
    # detection mechanism. Note however that just because it's empty,
    # doesn't mean that every possible reference has been detected.
    problems = {
        "conjugation-not-found": [],
    }

    conjugated = get_conjugated_law_names(index)

    # Now iterate through all the laws and parse their contents.
    for law_entry in index.xpath("/index/law-entries/law-entry"):
        law_nr = law_entry.attrib["nr"]
        law_year = int(law_entry.attrib["year"])

        law_ref_entry = E(
            "law-ref-entry", {"law-nr": str(law_nr), "law-year": str(law_year)}
        )

        law = etree.parse(XML_FILENAME % (law_year, law_nr)).getroot()

        sens = law.xpath("//sen[not(ancestor::footnotes)]")
        for sen in sens:
            # We'll be butchering this so better make a copy.
            chunk = sen.text or ""

            # The outer references we'll be looking for (i.e.
            # `nr\. (\d{1,3}\/\d{4})`), may appear multiple times in the same
            # sentence. This will confuse the relevant searching mechanism by
            # it finding again an outer reference that it has already found.
            #
            # To remedy this, we will keep an offset which will always be
            # either 0 as defined here, or equal to the last
            # `potentials_outer_end`, so that we continue the search for the
            # outer reference from where we left off in the previous iteration,
            # rather than from the start of the chunk every time.
            potentials_outer_start_offset = 0

            nrs_and_years = re.findall(
                r"(?<!EES-nefndarinnar )(?<!auglýsingu )nr\. (\d{1,3}\/\d{4})", chunk
            )
            for nr_and_year in nrs_and_years:

                # NOTE: Every law has a name, so if this doesn't exist,
                # `nr_and_year` cannot refer to a law unless there's a mistake
                # in the legal codex itself.
                #
                # TODO: We might want to collect these and figure out if there
                # are any such mistakes, or if we can further utilize these
                # references even if they don't refer to laws.
                if nr_and_year not in conjugated:
                    problems["conjugation-not-found"].append(sen)
                    continue

                # Short-hands.
                accusative = conjugated[nr_and_year]["accusative"]
                dative = conjugated[nr_and_year]["dative"]
                genitive = conjugated[nr_and_year]["genitive"]

                # The outer and inner references we will build.
                reference = ""

                # Becomes True if the underlying mechanism is able to
                # conclusively determine that the inner reference has been
                # parsed completely and correctly. This typically happens when
                # we run into key words like "skv." or "sbr.".
                certain_about_inner = False

                # Possible permutations of how the outer part of reference
                # might be construed.
                # FIXME: This might be better turned into a regex.
                potential_start_guesses = [
                    "%s, nr. %s" % (accusative, nr_and_year),
                    "%s, nr. %s" % (dative, nr_and_year),
                    "%s, nr. %s" % (genitive, nr_and_year),
                    "%s nr. %s" % (accusative, nr_and_year),
                    "%s nr. %s" % (dative, nr_and_year),
                    "%s nr. %s" % (genitive, nr_and_year),
                    "lög nr. %s" % nr_and_year,
                    "lögum nr. %s" % nr_and_year,
                    "laga nr. %s" % nr_and_year,
                ]

                # A string holding potential parts of an inner reference. Gets
                # continuously analyzed and chipped away at, as we try to
                # include as much as we can.
                potentials = ""

                # NOTE: We call this a starting location, but we're parsing
                # backwards into the string from the starting location, even
                # though we're looking for the starting location forward.
                potentials_outer_start = -1
                potentials_outer_end = -1

                # Begin by finding out where the next outer reference starts.
                # The `found_guess` variable is used after the loop to figure
                # out where it ends and to decide the search offset in the next
                # round of scanning the chunk.
                for potential_start_guess in potential_start_guesses:
                    attempt = chunk.find(
                        potential_start_guess, potentials_outer_start_offset
                    )

                    if potentials_outer_start == -1 or (
                        attempt > -1 and attempt < potentials_outer_start
                    ):
                        potentials_outer_start = attempt

                        # Record the outer end location so that we can decide
                        # where to end the label constructed later.
                        potentials_outer_end = attempt + len(potential_start_guess)

                # Remember where to pick up the search for different
                # permutations of outer references, in the next outer reference
                # to be processed.
                potentials_outer_start_offset = potentials_outer_end

                if potentials_outer_start > -1:

                    # Potentials are the string that potentially contains the
                    # inner parts of a reference, i.e. without the law's number
                    # and name.
                    potentials = chunk[:potentials_outer_start].strip()

                    # Check for inner parts of reference for as long as we can.
                    # FIXME: This `beendone` loop-checking thing is ridiculous.
                    # We should remove things from `potentials` until it's
                    # empty and break there.
                    beendone = 0
                    while True:

                        # Check for inner reference components by iterating
                        # through known patterns.
                        for inner_pattern in inner_reference_patterns:
                            nrs_and_years = re.findall(inner_pattern, potentials)
                            if len(nrs_and_years) > 0:
                                match = nrs_and_years[0][0]
                                reference = "%s %s" % (match, reference)
                                potentials = potentials[: -len(match)].strip()

                                del match
                                continue

                        # Check if we can prove that we're done by using
                        # conclusive words.
                        for conclusion_part in conclusives:
                            p_len = len(potentials)
                            cp_len = len(conclusion_part)
                            if (
                                p_len >= cp_len
                                and potentials[-cp_len:].lower() in conclusives
                            ):
                                certain_about_inner = True
                                break
                        if certain_about_inner:
                            # Break outer loop as well.
                            break

                        # Check if we can prove that we're done by seeing if
                        # another outer reference can be found right before.
                        preceeding_law_match = re.findall(
                            r"(nr\. (\d{1,3}/\d{4}),)$", potentials
                        )
                        if len(preceeding_law_match):
                            pl_len = len(preceeding_law_match[0][0])
                            potentials = potentials[-pl_len:]
                            certain_about_inner = True
                            break

                        # Check for separators "og" and "eða".
                        # This could be done in a loop but that would just add
                        # code indenting.
                        separator = ""
                        for sep_try in ["og", "eða"]:
                            if len(potentials) < len(sep_try):
                                continue

                            if potentials[-len(sep_try) :] == sep_try:
                                separator = sep_try
                                break

                        if len(separator):
                            # If we run into a separator with no inner
                            # reference, then this is a reference to the entire
                            # law and not to an article within it. We may
                            # safely assume that we're done parsing.
                            if len(reference) == 0:
                                certain_about_inner = True
                                break

                            # The string ", " preceeding the separator
                            # indicates that what comes before is not a part of
                            # the same reference. We determine that the
                            # reference is complete.
                            if potentials.rstrip(separator)[-2:] == ", ":
                                certain_about_inner = True
                                break

                            # Otherwise, add matched separator and continue.
                            reference = "%s %s" % (separator, reference)
                            potentials = potentials[: -len(separator)].strip()

                            # Parts before separators (such "og" or "eða")
                            # follow a different format, because their context
                            # is determined by what comes after them.
                            #
                            # Consider:
                            #     a- og c–i-lið 9. tölul.
                            #
                            # The "a-" part doesn't make any sense except in
                            # the context of "c-i-lið" that comes afterward. We
                            # don't normally parse "a-" individually, we only
                            # parse it specifically after we run into an "og".
                            for and_inner_pattern in and_inner_reference_patterns:
                                nrs_and_years = re.findall(
                                    and_inner_pattern, potentials
                                )
                                if len(nrs_and_years) > 0:
                                    match = nrs_and_years[0][0]
                                    reference = "%s %s" % (match, reference)
                                    potentials = potentials[: -len(match)].strip()
                                    del match

                                del nrs_and_years

                            # We don't need to concern ourselves more with this
                            # iteration. Moving on.
                            continue

                        # If we can't find any matches anymore, it means that
                        # we're out of the inner part of the reference or into
                        # something that we don't support yet.
                        if beendone > 100:
                            print("\n[ LOOP DETECTED ]: %s" % potentials)
                            stat_loop_count += 1
                            break
                        beendone += 1

                    # Indentation of inner reference being finished.
                    pass

                # May contain stray whitespace due to concatenation.
                reference = reference.strip()

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

                # Generate an XPath to the current node containing the
                # reference.
                location = make_xpath_from_node(sen)

                if certain_about_inner:

                    # To adhere to our established norm of separating law
                    # number and law year.
                    target_law_nr, target_law_year = nr_and_year.split("/")

                    # Either find or construct the node for the given entry.
                    ref_node = law_ref_entry.find('node[@location="%s"]' % location)
                    if ref_node is None:
                        ref_node = E(
                            "node",
                            {
                                "location": location,
                                "text": chunk,
                            },
                        )
                        law_ref_entry.append(ref_node)

                    ref_node.append(
                        E(
                            "reference",
                            {
                                "link-label": link_label,
                                "inner-reference": reference,
                                "law-nr": target_law_nr,
                                "law-year": target_law_year,
                            },
                        )
                    )
                    xml_ref_doc.append(law_ref_entry)

                    stat_conclusive_count += 1

                else:
                    print("-------------")
                    print("- Processing: %s/%s" % (law_nr, law_year))
                    print("- Chunk:      %s" % chunk)
                    print("- Potentials: %s" % potentials)
                    print("- Law:        %s" % nr_and_year)
                    print("- Accusative: %s" % accusative)
                    # print("Dative: %s" % dative)  # Unimplemented, but we need it.
                    print("- Genitive:   %s" % genitive)
                    print("- Reference:  %s" % reference)
                    print(
                        "- Conclusive: %s"
                        % ("true" if certain_about_inner else "false")
                    )

                    stat_inconclusive_count += 1

            # Indent for: `for nr_and_year in matches`
            pass

        print(".", end="", flush=True)

    # Apply statistics to XML.
    xml_ref_doc.attrib["stat-loop-count"] = str(stat_loop_count)
    xml_ref_doc.attrib["stat-inconclusive-count"] = str(stat_inconclusive_count)
    xml_ref_doc.attrib["stat-conclusive-count"] = str(stat_conclusive_count)
    write_xml(xml_ref_doc, XML_REFERENCES_FILENAME, skip_prettyprint_hack=True)

    print(" done")
