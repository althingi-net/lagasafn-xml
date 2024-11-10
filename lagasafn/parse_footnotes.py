#
#  Parsing functions for footnotes (as a collection) and individual footnotes.
#  This is a rather complex set of functions, and should probably be simplified.
#
import copy
from lxml.builder import E
import re
from formencode.doctest_xml_compare import xml_compare
from lagasafn.contenthandlers import regexify_markers
from lagasafn.contenthandlers import strip_markers
from lagasafn.contenthandlers import next_footnote_sup
from lagasafn.utils import UnexpectedClosingBracketException
from lagasafn.utils import super_iter
from lagasafn.utils import find_unmatched_closing_bracket
from lagasafn.pathing import make_xpath_from_node


def parse_footnotes(parser):
    if not (parser.line == "<i>" and parser.peeks() == "<small>"):
        return False
    
    parser.consume("<i>")
    parser.consume("<small>")

    # Footnotes section. Contains footnotes.
    parser.enter("footnotes")

    parser.footnotes = E("footnotes")

    # Try an append the footnotes to whatever's appropriate given the
    # content we've run into.
    if parser.trail_last().tag == "num-and-date":
        parser.note("Appending footnotes to law after finding num-and-date.")
        parser.law.append(parser.footnotes)
    elif parser.trail_last().tag == "appendix":
        parser.note("Appending footnotes to appendix after finding appendix.")
        parser.appendix.append(parser.footnotes)
    elif parser.trail_last().tag == "chapter":
        parser.note("Appending footnotes to chapter after finding chapter.")
        parser.chapter.append(parser.footnotes)
    elif parser.trail_last().tag == "ambiguous-section":
        parser.note("Appending footnotes to ambiguous section after finding ambiguous section.")
        parser.ambiguous_section.append(parser.footnotes)
    elif parser.mark_container is not None:
        parser.mark_container.append(parser.footnotes)
    elif parser.art is not None:
        # Most commonly, footnotes will be appended to articles.
        parser.note("Appending footnotes to article after finding article.")
        parser.art.append(parser.footnotes)
    elif parser.subart is not None:
        # In law that don't actually have articles, but only
        # subarticles (which are rare, but do exist), we'll need to
        # append the footnotes to the subarticle instead of the
        # article.
        parser.note("Appending footnotes to subarticle after finding subarticle.")
        parser.subart.append(parser.footnotes)
    else:
        parser.note("UNKNOWN LOCATION FOR FOOTNOTES")

    parser.trail_push(parser.footnotes)

    # This function is misnamed; it actually parses each footnote available for this footnotes block.
    parse_footnote(parser)
    while parser.line == "<sup style=\"font-size:60%\">":
        parse_footnote(parser)

    # TODO: This should be mandatory. We should throw an error if it's not found.
    parser.consume("</small>")

    parser.consume("</i>")

    parser.leave("footnotes")
    return True


def parse_footnote(parser):
    if not (parser.line == '<sup style="font-size:60%">' and parser.trail_last().tag in [
        "footnotes",
        "footnote",
    ]):
        return

    parser.enter("footnote")
    # We've found a footnote inside the footnote section!

    # Scroll past the closing tag, since we're not going to use its
    # content (see comment below).
    parser.scroll_until("</sup>")

    # Determine the footnote number.
    # In a perfect world, we should be able to get the footnote number
    # with a line like this:
    #
    #     footnote_nr = parser.collect_until(lines, '</sup>').strip(')')
    #
    # But it may in fact be wrong, like in 149. gr. laga nr. 19/1940,
    # where two consecutive footnotes are numbered as 1 below the
    # article. The numbers are correct in the reference in the article
    # itself, though. For this reason, we'll deduce the correct number
    # from the number of <footnote> tags present in the current
    # <footnotes> tag. That count plus one should be the correct
    # number.
    #
    # The footnote number, and in fact other numbers, are always used
    # as strings because they really function more like names rather
    # than numbers. So we make it a string right away.
    footnote_nr = str(len(parser.footnotes.findall("footnote")) + 1)

    # Create the footnote XML node.
    footnote = E("footnote")

    peek = parser.peeks()

    if parser.matcher.check(peek, r'<a href="(\/altext\/.*)">'):
        parser.enter("footnote-link")
        # This is a footnote regarding a legal change.
        href = "https://www.althingi.is%s" % parser.matcher.result()[0]

        # Retrieve the the content of the link to the external law
        # that we found.
        parser.scroll_until(r'<a href="(\/altext\/.*)">')
        footnote_sen = parser.collect_until("</a>")
        parser.next()   # Eat the </a> tag.

        # Update the footnote with the content discovered so far.
        footnote.attrib["href"] = href
        footnote.append(E("footnote-sen", footnote_sen))

        # If the content found so far adheres to the recognized
        # pattern of external law, we'll put that information in
        # attributes as well. (It should.)
        if parser.matcher.check(footnote_sen, r"L\. (\d+)\/(\d{4}), (\d+)\. gr\."):
            parser.enter("footnote-law")
            fn_law_nr, fn_law_year, fn_art_nr = parser.matcher.result()
            footnote.attrib["law-nr"] = fn_law_nr
            footnote.attrib["law-year"] = fn_law_year
            footnote.attrib["law-art"] = fn_art_nr
            parser.note("Footnote law: %s/%s, %s. gr." % (fn_law_nr, fn_law_year, fn_art_nr))
            parser.leave("footnote-law")
        
        parser.leave("footnote-link")

    if parser.line == "</sup>":
        parser.next()

    # Some footnotes don't contain a link to an external law like
    # above but rather some arbitrary information. In these cases
    # we'll need to parse the content differently. But also, sometimes
    # a link to an external law is followed by extra content, which
    # will also be parsed here and included in the footnote.
    #
    # We will gather everything we run across into a string called
    # `gathered`, until we run into a string that indicates that
    # either this footnote section has ended, or we've run across a
    # new footnote. Either one of the expected tags should absolutely
    # appear, but even if they don't, this will still error out
    # instead of looping forever, despite the "while True" condition,
    # because "next(lines)" will eventually run out of lines.
    gathered = ""

    while True:
        if parser.line in ["</small>", '<sup style="font-size:60%">']:
            break

        # The text we want is separated into lines with arbitrary
        # indenting and HTML comments which will later be removed.
        # As a result, meaningless whitespace is all over the
        # place. To fix this, we'll remove whitespace from either
        # side of the string, but add a space at the end, which
        # will occasionally result in a double whitespace or a
        # whitespace between tags and content. Those will be fixed
        # later, resulting in a neat string without any unwanted
        # whitespace.
        # parser.line implicitly strips the line.
        gathered += parser.line + " "

        # Get rid of HTML comments.
        gathered = re.sub(r'<!--.*?"-->', "", gathered)

        # Get rid of remaining unwanted whitespace (see above).
        gathered = (
            gathered.replace("  ", " ").replace("> ", ">").replace(" </", "</")
        )

        try:
            line = next(parser.lines)
        except:
            parser.dump_remaining(10)
            return


    # If extra content was found, we'll put that in a separate
    # sentence inside the footnote. If there already was a
    # <footnote-sen> because we found a link to an external law, then
    # there will be two sentences in the footnote. If this is the only
    # content found and there is no link to an external law, then
    # there will only be this one.
    if len(gathered):
        footnote.append(E("footnote-sen", gathered.strip()))

    # Explicitly state the footnote number as an attribute in the
    # footnote, so that a parser doesn't have to infer it from the
    # order of footnotes.
    footnote.attrib["nr"] = footnote_nr

    # Append the footnote to the `footnotes` node which is expected to
    # exist from an earlier iteration.
    parser.footnotes.append(footnote)

    if parser.line == "</small>":
        parser.enter("footnote-end")

        # At this point, the basic footnote XML has been produced,
        # enough to show the footnotes themselves below each article.
        # We will now see if we can parse the markers in the content
        # that the footnotes apply to, and add marker locations to the
        # footnote XML. We will then remove the markers from the text.
        # This way, the text and the marker location information are
        # separated.

        # The parent is the uppermost node above the footnotes but
        # below the document root node.
        parent = parser.footnotes.getparent()
        while parent is not None and parent.getparent() is not None and parent.getparent() != parser.law:
            parent = parent.getparent()

        # Closing markers have a tendency to appear after the sentence
        # that they refer to, like so:
        #
        # [Here is some sentence.] 2)
        #
        # This will result in two sentences:
        # 1. [Here is some sentence.
        # 2. ] 2)
        #
        # We'll want to combine these two, so we iterate through the
        # sentences that we have produced and find those that start
        # with closing markers and move the closing markers to the
        # previous sentence. This will make parsing end markers much
        # simpler. If the sentence where we found the closing marker
        # is empty, we'll delete it.
        #
        # In `close_mark_re` we allow for a preceding deletion mark
        # and move that as well, since it must belong to the previous
        # sentence if it precedes the closing marker that clear does.
        # (Happens in 2. mgr. 165. gr. laga nr. 19/1940.)
        close_mark_re = (
            r'((… <sup style="font-size:60%"> \d+\) </sup>)? ?\]? ?'
            r'<sup style="font-size:60%"> \d+\) </sup>)'
        )
        deletion_mark_re = r'(… <sup style="font-size:60%"> \d+\) </sup>)'
        nodes_to_kill = []

        if parent is None:
            parser.note("We think this should never happen; if you see this note, please investigate.")
            parser.leave("footnote-end")
            parser.leave("footnote")
            return

        parser.enter("iter-descendants")
        for desc in parent.iterdescendants():
            peek = desc.getnext()

            # When a closing marker (see the comment for the
            # `for`-loop above) appears at the beginning of the node
            # following the one with the opening marker, it will
            # usually be the next `sen` following a `sen`. It can also
            # happen that the closing marker appears in the
            # grand-child, so we also need to check for it there.
            #
            # Consider:
            #     <sen>[Some text</sen>
            #     <sen>] 2) Some other text</sen>
            #
            # But this code allows for:
            #
            #     <nr-title>[a.</nr-title>
            #     <paragraph>
            #         <sen>] 2) Some other text</sen>
            #
            # ...by also checking the immediate grand-child of the
            # current node.
            if peek is not None and peek.tag == "paragraph":
                peek_children = peek.getchildren()
                if len(peek_children) > 0:
                    peek = peek_children[0]

            # We have nothing to do here if the following node doesn't
            # exist or contain anything.
            if peek is None or peek.text is None:
                continue

            # Keep moving the closing markers from the next node
            # ("peek") to the current one ("desc"), until there are no
            # closing markers in the next node. (Probably there is
            # only one, but you never know.)
            while parser.matcher.check(peek.text.strip(), close_mark_re) and peek.tag != "mark-container":
                # Get the actual closing marker from the next node.
                stuff_to_move = parser.matcher.result()[0]

                # Add the closing marker to the current node.
                desc.text += stuff_to_move

                # Remove the closing marker from the next node.
                peek.text = re.sub(close_mark_re, "", peek.text, 1)
            while parser.matcher.check(peek.text.strip(), deletion_mark_re) and peek.tag != "mark-container":
                # FIXME: This loop and the one above are virtually identical.
                # Could use some code fancification.

                # Do the exact same thing for deletion markers.

                # Get the actual deletion marker from the next node.
                stuff_to_move = parser.matcher.result()[0]

                # Add the deletion marker to the current node.
                desc.text += stuff_to_move

                # Remove the deletion marker from the next node.
                peek.text = re.sub(deletion_mark_re, "", peek.text, 1)

            # If there's no content left in the next node, aside from
            # the closing markers that we just moved, then we'll put
            # the next node on a list of nodes that we'll delete
            # later. We can't delete it here because it will break the
            # iteration (parent.iterdescendants).
            #
            # We still wish to retain empty nodes that contain
            # attributes important for recreating the content visually.
            if len(peek.text) == 0 and "expiry-symbol-offset" not in peek.attrib:
                nodes_to_kill.append(peek)

        parser.leave("iter-descendants")

        # Delete nodes marked for deletion.
        for node_to_kill in nodes_to_kill:
            node_to_kill.getparent().remove(node_to_kill)

        opening_locations = []
        marker_locations = []
        for desc in parent.iterdescendants():

            # Leave the footnotes out of this, since we're only
            # looking for markers in text.
            if "footnotes" in [a.tag for a in desc.iterancestors()]:
                continue

            # Not interested if the node contains no text.
            if not desc.text:
                continue

            # Make sure that stray whitespace isn't getting in our way.
            desc.text = desc.text.strip()

            ###########################################################
            # Detection of opening and closing markers, "[" and "]",
            # respectively, as well as accompanied superscripted text
            # denoting their number.
            ###########################################################

            parser.enter("detect-opening-and-closing-marker")
            # Keeps track of where we are currently looking for
            # markers within the entity being checked.
            cursor = 0

            opening_found = desc.text.find("[", cursor)
            closing_found = desc.text.find("]", cursor)
            while opening_found > -1 or closing_found > -1:
                if opening_found > -1 and (
                    opening_found < closing_found or closing_found == -1
                ):
                    # We have found an opening marker: [

                    # Indicate that our next search for an opening tag will
                    # continue from here.
                    cursor = opening_found + 1

                    # We now try to figure out whether we want to mark an
                    # entire entity (typically a sentence), or if we want to
                    # mark a portion of it. If we want to mark a portion,
                    # `use_words` shall be True and the footnote XML will
                    # contain a `words` attribute will describe which words to
                    # enclose in square brackets.
                    use_words = True
                    if opening_found == 0:
                        unmatched_closing = find_unmatched_closing_bracket(desc.text[1:])
                        if unmatched_closing > -1:
                            # An unmatched closing bracket was found, but we
                            # need to make sure that it's truly at the end of
                            # the node's content.
                            closing_at_end = re.search(
                                r'\] <sup style="font-size:60%"> \d+\) </sup>$',
                                desc.text
                            )
                            # -1 because we're searching for the unmatched
                            # closing bracket from index 1, not index 0.
                            if (
                                closing_at_end is not None
                                and unmatched_closing == closing_at_end.start() - 1
                            ):
                                use_words = False
                        else:
                            # Found no unmatched closing bracket at all, which
                            # means that it will appear in some other node. We
                            # don't need to designate `words`.
                            use_words = False

                    middle_punctuation = None

                    words = None
                    instance_num = None
                    if use_words:
                        # We'll start with everything from the opening
                        # marker onward. Because of possible markers
                        # in the text that should end up in "words",
                        # we'll need to do a bit of processing to
                        # figure out where exactly the appropriate
                        # closing marker is located. Quite possibly,
                        # it's not simply the first one.
                        words = desc.text[opening_found + 1 :]

                        # Find the first non-paired closing marker.
                        closing_index = find_unmatched_closing_bracket(words)

                        # Cut the "words" variable appropriately. If
                        # closing_index wasn't found, it means that
                        # the "words" actually span beyond this
                        # sentence. Instead of cutting the words
                        # string (by -1 because the closing symbol
                        # wasn't found, which would make no sense), we
                        # leave it intact. The rest of the "words"
                        # string will be placed in an <end> element by
                        # the closing-marker mechanism.
                        if closing_index > -1:
                            words = words[:closing_index].strip()

                        if desc.text[opening_found + 1 + closing_index + 1] in [".", ",", ":", ";"]:
                            middle_punctuation = desc.text[opening_found + 1 + closing_index + 1]

                            # Add the middle-punctuation to the search string.
                            # It will be moved passed the opening marker by
                            # rendering mechanism. It is escaped so that "."
                            # doesn't match any symbol but only a literal ".".
                            # Incidentally the "," and ":" symbols also get
                            # escaped, but that has no effect.
                            words += r"\%s" % middle_punctuation

                        words = regexify_markers(words)

                        # Describes which instance of the regex is being
                        # referred to. This is needed when there are multiple
                        # instances of the text to replace, but not all of them
                        # should be marked as changed.
                        #
                        # This also takes care of the problem where the same
                        # instance gets replaced repeatedly, resulting in the
                        # wrong placement of range markers.
                        if desc.text[:opening_found] == "":
                            # When the `words` mechanism gets triggered but there
                            # is no content before it, there is a tendency to
                            # match the regex with empty space. This happens in
                            # "Ákvæði til bráðabirgða II laga nr. 82/2008"
                            # (153c). To avoid this, we decide that the
                            # `instance_num` should indeed just be 1.
                            instance_num = 1
                        else:
                            instance_num = len(re.findall(words, desc.text[:opening_found])) + 1

                    # We'll "pop" this list when we find the closing
                    # marker, as per below.
                    opening_locations.append({
                        "xpath": make_xpath_from_node(desc),
                        "words": words,
                        "middle_punctuation": middle_punctuation,
                        "instance_num": instance_num,
                    })

                elif closing_found > -1 and (
                    closing_found < opening_found or opening_found == -1
                ):
                    # We have found a closing marker: ]

                    cursor = closing_found + 1

                    # Find the footnote number next to the closing
                    # marker that we've found.
                    num = next_footnote_sup(desc, cursor)

                    # We have figured out the starting location in the
                    # former clause of the if-sentence.
                    try:
                        started_at = opening_locations.pop()
                    except IndexError:
                        # Error: We've run into an unexpected closing
                        # bracket. This happens when Parliament
                        # updates a law, and the changes are marked in
                        # the HTML files, but the corresponding
                        # opening bracket is missing. Typically, a law
                        # is being changed that has already been
                        # changed, and there should be two opening
                        # bracket ("[[") to mark the beginning of a
                        # change to a change, but there is only one
                        # ("[") due to human error.
                        #
                        # Please see the chapter "Patching errors in
                        # data" in the `README.md`.
                        #
                        # This exception spouts some details.
                        raise UnexpectedClosingBracketException(desc)

                    ended_at = {
                        "xpath": make_xpath_from_node(desc),
                        "words": None,  # Maybe filled later.
                        "middle_punctuation": None,  # Maybe filled later.
                        "instance_num": None,  # Maybe filled later.
                    }

                    # We trigger the `words` mechanism also is there is a
                    # deletion marker in the end. Otherwise this can screw up
                    # the order of markers.
                    # Occurs at the end of 1. mgr. 12. gr. laga nr. 78/2002 (153c).
                    ends_with_deletion = re.search(
                        r'… <sup style="font-size:60%"> \d+\) <\/sup>$',
                        desc.text
                    ) is not None

                    # Decide whether to use `words` or not.
                    use_words = started_at["words"] is not None or ends_with_deletion

                    # If the start location had a "words" attribute,
                    # indicating that a specific set of words should
                    # be marked, then we'll copy that attribute here
                    # to the end location, so that the <start> and
                    # <end> tags will get truncated into a unified
                    # <location> tag...
                    middle_punctuation = None
                    instance_num = None
                    if use_words:
                        # ...except, if it turns out that we're
                        # actually dealing with a different sentence
                        # than was specified in the start location,
                        # but the "words" attribute is being used, it
                        # means that a string is to be marked that
                        # spans more than one sentence.
                        #
                        # In such a case, the start location will
                        # determine the opening marker via its "words"
                        # attribute, but the end location (being
                        # processed here) will determine the closing
                        # marker with its distinct set of "words",
                        # each attribute containing the set of words
                        # contained in their respective sentences.

                        if parser.law.xpath(started_at["xpath"])[0] != desc:
                            unmatched_closing = find_unmatched_closing_bracket(desc.text)
                            words = regexify_markers(desc.text[: unmatched_closing])
                            if desc.text[unmatched_closing+1] in [".", ",", ":", ";"]:
                                middle_punctuation = desc.text[unmatched_closing+1]

                            # Not adding 1 here because it will always find the
                            # text once, if it's the first instance, because
                            # this is the closing marker. When dealing with the
                            # opening marker, we don't expect the content to
                            # arrive before `words`.
                            instance_num = len(re.findall(words, desc.text[:closing_found]))

                        else:
                            words = started_at["words"]
                            middle_punctuation = started_at["middle_punctuation"]
                            instance_num = started_at["instance_num"]

                        ended_at["words"] = words
                        ended_at["middle_punctuation"] = middle_punctuation
                        ended_at["instance_num"] = instance_num
                    else:
                        # Check for `middle-punctuation` with the closing
                        # marker, when there are no `words`, and we know that
                        # the markers encompass the entire element.
                        middle_punctuation_search = re.search(
                            r'([,.:]) ?<sup style="font-size:60%%"> %s\) <\/sup>' % num,
                            desc.text
                        )
                        if middle_punctuation_search is not None:
                            ended_at["middle_punctuation"] = middle_punctuation_search[1]

                    # Stuff our findings into a list of marker
                    # locations that can be appended to the footnote
                    # XML.
                    marker_locations.append(
                        {
                            "num": int(num) if num is not None else None,
                            "type": "range",
                            # 'started_at' is determined from previous
                            # processing of the corresponding opening
                            # marker.
                            "started_at": started_at,
                            # 'ended_at' is determined from the processing
                            # of the closing marker, which is what we just
                            # performed.
                            "ended_at": ended_at,
                        }
                    )

                # Check again for the next opening and closing
                # markers, except from our cursor, this time.
                closing_found = desc.text.find("]", cursor)
                opening_found = desc.text.find("[", cursor)

            parser.leave("detect-opening-and-closing-marker")

            ##########################################################
            # Detection of deletion markers, indicated by the "…"
            # character, followed by superscripted text indicating its
            # reference number.
            ##########################################################

            # Keeps track of where we are currently looking for
            # markers within the entity being checked, like above.
            cursor = 0

            # NOTE: Making the space optional before "<sup" only serves to fix
            # lög nr. 132/1999 (153c) at this moment. But it doesn't seem to
            # break anything else. -2024-11-03.
            # NOTE: Making the optional "]" appear between the hellip and
            # "<sup" occurs in 2. mgr. 63. gr. laga nr. 8/1962 (153c). Probably
            # also occurs elsewhere.
            deletion_found = -1
            deletion_search = re.search(r'… ?[,.;:]?\]? ?<sup', desc.text[cursor:])
            if deletion_search is not None:
                deletion_found = deletion_search.start()

            if deletion_found > -1:
                parser.enter("detect-deletion-marker")

            while deletion_found > -1:
                # Keep track of how far we've already searched.
                cursor = deletion_found + 1

                # Find the footnote number next to the deletion marker
                # that we've found.
                num = next_footnote_sup(desc, cursor)

                # len('</sup>') == 6
                sup_end = desc.text.find("</sup>", deletion_found + 1) + 6

                # We'll take the text that comes before and after the
                # deletion mark, and replace their markers with
                # regular expressions that match them, both with the
                # markers and without them. This way, any mechanism
                # intended to put the deletion markers back in works
                # on the text regardless of whether the other deletion
                # or replacement markers are already there or not.
                before_mark = "^" + regexify_markers(desc.text[:deletion_found])
                after_mark = regexify_markers(desc.text[sup_end:]) + "$"

                # Deletion markers are styled like this when they
                # indicate deleted content immediately before a comma:
                #
                # "bla bla bla …, 2) yada yada"
                #
                # The native text without deletion markers would look
                # like this:
                #
                # "bla bla bla, yada yada"
                #
                # We therefore need to check for a comma immediately
                # following the deletion symbol itself (…). If it's
                # there, then well communicate the need to add it in
                # the middle of the deletion marker via the attribute
                # "middle-punctuation". For possible future
                # compatibility with other symbols, we'll put in a
                # comma as the value and expect the marker renderer to
                # use that directly instead of assuming a comma.
                middle_punctuation = None
                if desc.text[deletion_found + 1 : deletion_found + 2] == ",":
                    middle_punctuation = ","

                marker_locations.append(
                    {
                        "num": int(num),
                        "type": "deletion",
                        "started_at": {
                            "xpath": make_xpath_from_node(desc),
                            "middle_punctuation": middle_punctuation,
                            "before_mark": before_mark,
                            "after_mark": after_mark
                        }
                    }
                )

                deletion_found = desc.text.find("…", cursor)

            parser.leave_if_last("detect-deletion-marker")

            ##########################################################
            # Detect single superscripted numbers, which indicate
            # points that belong to a reference without indicating any
            # kind of change to the text itself. Such markers will be
            # called pointers from now on.
            ##########################################################

            # Keeps track of where we are currently looking for
            # pointers within the entity being checked, like above.
            cursor = 0

            pointer_found = desc.text.find('<sup style="font-size:60%">', cursor)
            if pointer_found > -1:
                parser.enter("detect-pointer")

            while pointer_found > -1:
                # Keep track of how far we've already searched.
                cursor = pointer_found + 1

                # If this is in fact a closing or deletion marker,
                # then either the symbol "]" or "…" will appear
                # somewhere among the 3 characters before the
                # superscript. Their exact location may depend on the
                # applied styling or punctuation, since spacing style
                # differs slightly according to the location of
                # closing and deletion markers, and punctuation can
                # appear between the symbol and superscript (i.e.
                # "bla]. 2)".
                chars_before_start = pointer_found - 3 if pointer_found >= 3 else 0
                chars_before = desc.text[chars_before_start:pointer_found].strip()
                if "…" in chars_before or "]" in chars_before:
                    # This is a closing or deletion marker, which
                    # we're not interested in at this point.
                    pointer_found = desc.text.find(
                        '<sup style="font-size:60%">', cursor
                    )
                    continue

                # Catch all the superscript content, so that we may
                # its length, and while we're at it, grab the footnote
                # number as well.
                parser.matcher.check(
                    desc.text[pointer_found:],
                    r'(<sup style="font-size:60%"> (\d+)\) </sup>)',
                )
                sup, num = parser.matcher.result()

                # Determine where the symbol ends.
                sup_end = pointer_found + len(sup)

                # We'll take the text that comes before and after the
                # pointer, and replace their markers with regular
                # expressions that match them, both with the markers
                # and without them. This way, any mechanism intended
                # to put the deletion markers back in works on the
                # text regardless of whether the other deletion or
                # replacement markers are already there or not.
                before_mark = "^" + regexify_markers(desc.text[:pointer_found])
                after_mark = regexify_markers(desc.text[sup_end:]) + "$"

                marker_locations.append(
                    {
                        "num": int(num),
                        "type": "pointer",
                        "started_at": {
                            "xpath": make_xpath_from_node(desc),
                            "before_mark": before_mark,
                            "after_mark": after_mark,
                        },
                    }
                )

                pointer_found = desc.text.find(
                    '<sup style="font-size:60%">', cursor
                )

            parser.leave_if_last("detect-pointer")

            ##########################################################
            # At this point, we're done processing the following:
            # 1. Opening/closing markers ("[" and "]")
            # 2. Deletion markers ("…")
            # 3. Pointers (indicated by superscripted number)
            ##########################################################

            # Now that we're done processing the markers and can add
            # them to the footnotes in XML format, we'll delete them
            # from the text itself. This may leave spaces on the edges
            # which we'll remove as well.
            desc.text = strip_markers(desc.text).strip()

        parser.leave('footnote-end')

        # If no marker locations have been defined, we have nothing
        # more to do here.
        if len(marker_locations) == 0:
            parser.leave("footnote")
            return

        # Finally, we'll start to build and add the location XML to
        # the footnotes, out of all this information we've crunched
        # from the text!

        # We'll want to be able to "peek" backwards easily, so we'll
        # use the super_iterator. We could also use enumerate() but we
        # figure that using the peek function is more readable than
        # playing around with iterators.
        parser.enter("marker-locations")
        marker_locations = super_iter(marker_locations)

        for ml in marker_locations:
            # If the num is None, then the range is not attributable
            # to a footnote. This occurs in 4. mgr. 10. gr. laga nr.
            # 40/2007 to indicate that a lowercase letter has been
            # made uppercase as an implicit result of a legal change
            # that removed the first portion of the sentence. As far
            # as we can tell, this is not a rule but rather just the
            # explanation in that case. Unspecified ranges may
            # presumably exist for other reasons.
            #
            # When this happens, we will respond by adding an
            # <unspecified-ranges> tag immediately following the
            # <footnotes> tag that already exists. We will then then
            # simply stuff the <location> element in there instead of
            # the footnote that we should find in cases when `num` is
            # an integer (i.e. referring to a numbered footnote).
            if ml["num"] is None:
                # Find the index where we'll want to add the new
                # <unspecified-ranges> element.
                new_index = parser.footnotes.getparent().index(parser.footnotes) + 1

                # Create the new <unspecified-ranges> element.
                location_target = E("unspecified-ranges")

                # Add the new element immediately after the
                # <footnotes> element.
                parser.footnotes.getparent().insert(new_index, location_target)
            else:
                # Get the marker's appropriate footnote XML.
                location_target = parser.footnotes.getchildren()[ml["num"] - 1]

            # Create the location XML node itself.
            location = E("location", {"type": ml["type"]})

            if ml["type"] in ["pointer", "deletion"]:
                location.attrib["xpath"] = ml["started_at"]["xpath"]
                location.attrib["before-mark"] = ml["started_at"]["before_mark"]
                location.attrib["after-mark"] = ml["started_at"]["after_mark"]
                # FIXME: This if-sentence is ridiculous. We should rather make
                # sure that `middle_punctuation` always exists in
                # `ml["started_at"]`, even as `None`.
                if "middle_punctuation" in ml["started_at"] and ml["started_at"]["middle_punctuation"] is not None:
                    location.attrib["middle-punctuation"] = ml["started_at"]["middle_punctuation"]

                location_target.append(location)

            elif ml["type"] == "range":
                # If the starting and ending locations are identical,
                # we will only want a <location> element to denote the
                # marker's locations.
                started_at = ml["started_at"]
                ended_at = ml["ended_at"]
                if (
                    started_at["xpath"] == ended_at["xpath"]
                    and started_at["words"] == ended_at["words"]
                ):
                    # NOTE: We use `ended_at` consciously, because for example
                    # `middle_punctuation` rules the closing marker and not the
                    # opening marker.
                    location.attrib["xpath"] = ended_at["xpath"]
                    if ended_at["words"] is not None:
                        location.attrib["words"] = ended_at["words"]
                    if ended_at["middle_punctuation"] is not None:
                        location.attrib["middle-punctuation"] = ended_at["middle_punctuation"]
                    if ended_at["instance_num"] is not None:
                        location.attrib["instance-num"] = str(ended_at["instance_num"])
                else:
                    start = E("start")
                    end = E("end")

                    start.attrib["xpath"] = started_at["xpath"]
                    end.attrib["xpath"] = ended_at["xpath"]

                    if started_at["words"] is not None:
                        start.attrib["words"] = started_at["words"]
                    if ended_at["words"] is not None:
                        end.attrib["words"] = ended_at["words"]

                    if started_at["middle_punctuation"] is not None:
                        start.attrib["middle-punctuation"] = started_at["middle_punctuation"]
                    if ended_at["middle_punctuation"] is not None:
                        end.attrib["middle-punctuation"] = ended_at["middle_punctuation"]

                    if started_at["instance_num"] is not None:
                        start.attrib["instance-num"] = str(started_at["instance_num"])
                    if ended_at["instance_num"] is not None:
                        end.attrib["instance-num"] = str(ended_at["instance_num"])

                    location.append(start)
                    location.append(end)

                # If the location XML that we're adding is identical
                # to a previous location node in the same footnote
                # node, then instead of adding the same location node
                # again, we'll configure the previous one as
                # repetitive. We assume that if the same words are
                # marked twice, that all instances of the same words
                # should be marked in the given element.
                #
                # This is done to make it easier to use the XML when
                # the same set of words should be marked repeatedly in
                # the same sentence.
                twin_found = False
                for maybe_twin in location_target.findall("location"):

                    # We need to compare with the previous elements without the
                    # `repeat` attribute, because otherwise we run into
                    # differences when the repetitition happens more than once.
                    maybe_twin_copy = copy.deepcopy(maybe_twin)
                    if "repeat" in maybe_twin_copy.attrib:
                        del maybe_twin_copy.attrib["repeat"]

                    if xml_compare(maybe_twin_copy, location):
                        maybe_twin.attrib["repeat"] = "true"
                        twin_found = True
                        break

                if not twin_found:
                    # Finally, we add the location node to the footnote
                    # node (or unspecified-ranges node).
                    location_target.append(location)

        parser.leave("marker-locations")
        parser.trail_push(footnote)

    # Eat a final </a> if we have one.
    if parser.line == "</a>":
        parser.next()

    parser.leave("footnote")
