#
#  Parsing functions for footnotes (as a collection) and individual footnotes.
#  This is a rather complex set of functions, and should probably be simplified.
#
from lxml.builder import E
import re
from lagasafn.contenthandlers import generate_ancestors
from lagasafn.contenthandlers import regexify_markers
from lagasafn.contenthandlers import strip_markers
from lagasafn.utils import super_iter


def parse_footnotes(parser):
    if parser.line != "<small>":
        return

    # Footnotes section. Contains footnotes.
    parser.enter("footnotes")

    parser.footnotes = E("footnotes")

    # Try an append the footnotes to whatever's appropriate given the
    # content we've run into.
    if parser.trail_last().tag == "num-and-date":
        print("Appending footnotes to law after finding num-and-date.")
        parser.law.append(parser.footnotes)
    elif parser.trail_last().tag == "chapter":
        print("Appending footnotes to chapter after finding chapter.")
        parser.chapter.append(parser.footnotes)
    elif parser.trail_last().tag == "ambiguous-section":
        print("Appending footnotes to ambiguous section after finding ambiguous section.")
        parser.ambiguous_section.append(parser.footnotes)
    elif parser.art is not None:
        # Most commonly, footnotes will be appended to articles.
        print("Appending footnotes to article after finding article.")
        parser.art.append(parser.footnotes)
    elif parser.subart is not None:
        # In law that don't actually have articles, but only
        # subarticles (which are rare, but do exist), we'll need to
        # append the footnotes to the subarticle instead of the
        # article.
        print("Appending footnotes to subarticle after finding subarticle.")
        parser.subart.append(parser.footnotes)
    else:
        print("UNKNOWN LOCATION FOR FOOTNOTES")

    parser.next()
    parser.trail_push(parser.footnotes)

    # This function is misnamed; it actually parses each footnote available for this footnotes block.
    parse_footnote(parser)

    if parser.line == "</small>":
        parser.next()

    parser.leave("footnotes")


def parse_footnote(parser):
    print("Parsing footnote? Line: '%s' - Trail last: '%s'" % (parser.line, parser.trail_last().tag))
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
            parser.leave()
        
        parser.leave()

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
        if parser.peeks() in ["</small>", '<sup style="font-size:60%">']:
            break
        else:
            # The text we want is separated into lines with arbitrary
            # indenting and HTML comments which will later be removed.
            # As a result, meaningless whitespace is all over the
            # place. To fix this, we'll remove whitespace from either
            # side of the string, but add a space at the end, which
            # will occasionally result in a double whitespace or a
            # whitespace between tags and content. Those will be fixed
            # later, resulting in a neat string without any unwanted
            # whitespace.
            gathered += next(parser.lines).strip() + " "

        # Get rid of HTML comments.
        gathered = re.sub(r'<!--.*?"-->', "", gathered)

        # Get rid of remaining unwanted whitespace (see above).
        gathered = (
            gathered.replace("  ", " ").replace("> ", ">").replace(" </", "</")
        )

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

    if parser.peeks() == "</small>":
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
        nodes_to_kill = []

        if parent == None:
            parser.leave()
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
            while parser.matcher.check(peek.text, close_mark_re):
                # Get the actual closing marker from the next node.
                stuff_to_move = parser.matcher.result()[0]

                # Add the closing marker to the current node.
                desc.text += stuff_to_move

                # Remove the closing marker from the next node.
                peek.text = re.sub(close_mark_re, "", peek.text, 1)

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

        parser.leave()

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

                    # Indicate that our next search for an opening tag
                    # will continue from here.
                    cursor = opening_found + 1

                    # Get the ancestors of the node (see function's
                    # comments for details.)
                    ancestors = generate_ancestors(desc, parent)

                    # We now try to figure out whether we want to mark
                    # an entire entity (typically a sentence), or if
                    # we want to mark a portion of it. If we want to
                    # mark a portion, "use_words" shall be True and
                    # the footnote XML will contain something like
                    # this:
                    #
                    #    <sen words="some marked text">2</sen>
                    #
                    # Instead of:
                    #
                    #    <sen>2</sen>
                    #

                    # At this point, the variable `opening_found`
                    # contains the location of the first opening
                    # marker (the symbol "]") in the current node's
                    # text.

                    # Find the opening marker after the current one,
                    # if it exists.
                    next_opening = desc.text.find("[", opening_found + 1)

                    # Check whether the next opening marker, if it
                    # exists, is between the current opening marker
                    # and the next closing marker.
                    no_opening_between = (
                        next_opening == -1 or next_opening > closing_found
                    )

                    # Use "words" if 1) the opening marker is at the
                    # start of the sentence and 2) there is also a
                    # closing marker found but 3) there's no opening
                    # marker between the current marker and its
                    # corresponding closing marker.
                    partial_at_start = (
                        opening_found == 0
                        and closing_found > -1
                        and no_opening_between
                    )

                    # Check if the opening and closing markers
                    # encompass the entire entity. In these cases, it
                    # makes no sense to use "words".
                    all_encompassing = all(
                        [
                            opening_found == 0,
                            no_opening_between,
                            desc.text[0] == "[",
                            parser.matcher.check(
                                desc.text[closing_found:],
                                r'\] <sup style="font-size:60%"> \d+\) </sup>$',
                            ),
                        ]
                    )

                    # Boil this logic down into the question: to use
                    # words or not to use words?
                    use_words = (
                        opening_found > 0 or partial_at_start
                    ) and not all_encompassing

                    if use_words:
                        # We'll start with everything from the opening
                        # marker onward. Because of possible markers
                        # in the text that should end up in "words",
                        # we'll need to do a bit of processing to
                        # figure out where exactly the appropriate
                        # closing marker is located. Quite possibly,
                        # it's not simply the first one.
                        words = desc.text[opening_found + 1 :]

                        # Eliminate **pairs** of opening and closing
                        # markers beyond the opening marker we're
                        # currently dealing with. When this has been
                        # accomplished, the next closing marker should
                        # be the one that goes with the opening marker
                        # that we're currently dealing with. Example:
                        #
                        #     a word [and another] that says] boo
                        #
                        # Should become:
                        #
                        #     a word and another that says] boo
                        #
                        # Note that the opening/closing marker pair
                        # around "and another" have disappeared
                        # because they came in a pair. With such pairs
                        # removed, we can conclude our "words"
                        # variable from the remaining non-paired
                        # closing marker, and the result should be:
                        #
                        #     a word and another that says
                        #
                        words = re.sub(
                            r'\[(.*?)\] <sup style="font-size:60%"> \d+\) </sup>',
                            r"\1",
                            words,
                        )

                        # Find the first non-paired closing marker.
                        closing_index = words.find("]")

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
                            words = words[:closing_index]

                        # Explicitly remove marker stuff, even though
                        # most likely it will already be gone because
                        # the marker parsing implicitly avoids
                        # including them. Such removal may leave stray
                        # space that we also clear.
                        words = strip_markers(words).strip()

                        # Add the "words" attribute to the last element.
                        ancestors[-1].attrib["words"] = words

                    # We'll "pop" this list when we find the closing
                    # marker, as per below.
                    opening_locations.append(ancestors)

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

                    # Get the ancestors of the node (see function's
                    # comments for details.)
                    ancestors = generate_ancestors(desc, parent)

                    # If the start location had a "words" attribute,
                    # indicating that a specific set of words should
                    # be marked, then we'll copy that attribute here
                    # to the end location, so that the <start> and
                    # <end> tags will get truncated into a unified
                    # <location> tag...
                    if "words" in started_at[-1].attrib:
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
                        sen_nr = str(order_among_siblings(desc))
                        if desc.tag == "sen" and sen_nr != started_at[-1].text:
                            # Remove pairs of opening/closing markers
                            # from the "words", so that we find the
                            # correct closing marker. (See comment on
                            # same process in processing of opening
                            # markers above.)
                            words = re.sub(
                                r'\[(.*?)\] <sup style="font-size:60%"> \d+\) </sup>',
                                r"\1",
                                words,
                            )
                            words = desc.text[: desc.text.find("]")]
                        else:
                            words = started_at[-1].attrib["words"]

                        ancestors[-1].attrib["words"] = words

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
                            "ended_at": ancestors,
                        }
                    )

                # Check again for the next opening and closing
                # markers, except from our cursor, this time.
                closing_found = desc.text.find("]", cursor)
                opening_found = desc.text.find("[", cursor)

            parser.leave()

            ##########################################################
            # Detection of deletion markers, indicated by the "…"
            # character, followed by superscripted text indicating its
            # reference number.
            ##########################################################

            # Keeps track of where we are currently looking for
            # markers within the entity being checked, like above.
            cursor = 0


            deletion_found = desc.text.find("…", cursor)
            if deletion_found > -1:
                parser.enter("detect-deletion-marker")

            while deletion_found > -1:
                # Keep track of how far we've already searched.
                cursor = deletion_found + 1

                # If the deletion marker is immediately followed by a
                # closing link tag, it means that this is in fact not
                # a deletion marker, but a comment. They are not
                # processed here, so we'll update the deletion_found
                # variable (in the same way as is done at the end of
                # this loop) and continue.
                if desc.text[cursor : cursor + 5] == " </a>":
                    deletion_found = desc.text.find("…", cursor)
                    continue

                # Find the footnote number next to the deletion marker
                # that we've found.
                num = next_footnote_sup(desc, cursor)

                # If no footnote number is found, then we're not
                # actually dealing with a footnote, but rather the "…"
                # symbol being used for something else. For what,
                # exactly, is undetermined as of yet.
                if num is None or num == "":
                    deletion_found = desc.text.find("…", cursor)
                    continue

                # See function's comments for details.
                ancestors = generate_ancestors(desc, parent)

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
                if desc.text[deletion_found + 1 : deletion_found + 2] == ",":
                    ancestors[-1].attrib["middle-punctuation"] = ","

                # Assign the regular expressions for the texts before
                # and after the deletion mark, to the last node in the
                # location XML.
                if before_mark:
                    ancestors[-1].attrib["before-mark"] = before_mark
                if after_mark:
                    ancestors[-1].attrib["after-mark"] = after_mark

                marker_locations.append(
                    {
                        "num": int(num),
                        "type": "deletion",
                        "started_at": ancestors,
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

                # See function's comments for details.
                ancestors = generate_ancestors(desc, parent)

                # If this is in fact a closing or deletion marker,
                # then either the symbol "[" or "…" will appear
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

                # Assign the regular expressions for the texts before
                # and after the pointer, to the last node in the
                # location XML.
                if before_mark:
                    ancestors[-1].attrib["before-mark"] = before_mark
                if after_mark:
                    ancestors[-1].attrib["after-mark"] = after_mark

                marker_locations.append(
                    {
                        "num": int(num),
                        "type": "pointer",
                        "started_at": ancestors,
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
                for node in ml["started_at"]:
                    location.append(node)

                location_target.append(location)

            elif ml["type"] == "range":
                # If the starting and ending locations are identical,
                # we will only want a <location> element to denote the
                # marker's locations.
                started_at = ml["started_at"]
                ended_at = ml["ended_at"]
                if xml_lists_identical(started_at, ended_at):
                    for node in started_at:
                        location.append(node)
                else:
                    # If, however, the the starting and ending
                    # locations differ and we are not denoting a
                    # region of text with "words", we'll need
                    # sub-location nodes, <start> and <end>, within
                    # the <location> element, so that the opening and
                    # closing markers can be placed in completely
                    # different places.
                    start = E("start")
                    end = E("end")
                    for node in started_at:
                        start.append(node)
                    for node in ended_at:
                        end.append(node)

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
                    if xml_compare(maybe_twin, location):
                        maybe_twin.getchildren()[-1].attrib["repeat"] = "true"
                        twin_found = True
                        break

                if not twin_found:
                    # Finally, we add the location node to the footnote
                    # node (or unspecified-ranges node).
                    location_target.append(location)

        parser.leave()
        parser.trail_push(footnote)

    # Eat a final </a> if we have one.
    if parser.line == "</a>":
        parser.next()

    parser.leave("footnote")
