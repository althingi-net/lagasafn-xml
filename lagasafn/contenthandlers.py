import json
import os
import re
import string

from lagasafn.utils import Matcher
from lagasafn.utils import is_roman
from lagasafn.utils import order_among_siblings
from lagasafn.utils import strip_links
from lagasafn.utils import super_iter
from lagasafn.utils import terminal_width_and_height
from lxml.builder import E

SPLITMAP_FILENAME = os.path.join("data", "json-maps", "splitmap.json")


def begins_with_regular_content(argument):
    # Checks if the given argument begins with regular text, as
    # opposed to an article or something of the sort. It is used to
    # determine if we've found content after a numart, that we don't
    # know where to place.
    #
    # WARNING: This was a test that seemed to work in the first try,
    # which was a surprise. It may require more sophisticated means
    # of determining regular content in all cases.
    question = strip_markers(strip_links(argument)).strip()
    if len(question) and question[0] != "<":
        return True
    else:
        return False


def regexify_markers(text):
    """
    Replaces markers in given text with regex that will match those same
    markers. The point is to have a regex that will match the string both with
    and without markers.
    """

    # These must be escaped so that they are not interpreted as regex from
    # renderer's point of view.
    text = text.replace("(", "\)")
    text = text.replace(")", "\)")

    # Opening markers.
    text = re.sub(r"\[ ?", r"(\[? ?)?", text)

    # Closing markers.
    # NOTE: The three backslashes before the closing parentheses is because
    # we must seek the string after it has been modified by the
    # parentheses-escaping code above. We're looking for "\)" instead of ")".
    text = re.sub(
        r'\],?\.? ?<sup style="font-size:60%"> ?\d+\\\) ?</sup>,? ?',
        r'\.?(\],?\.? ?<sup( style="font-size:60%")?> ?\\d+\) ?</sup>)?,? ?',
        text,
    )

    # Deletion markers.
    # NOTE: See comment for closing markers above.
    text = re.sub(
        r'… <sup style="font-size:60%"> ?\d+\\\) ?</sup>,? ?',
        r'(… <sup( style="font-size:60%")?> ?\\d+\) ?</sup>)?,? ?',
        text,
    )

    # FIXME: This is unexplained.
    text = text.replace(" ,", r" ?,")

    # Remove stray spaces.
    text = text.strip()

    return text


def strip_markers(text):
    """
    Strips markers from text and cleans up resulting weirdness.
    """

    text = text.replace("…", "")
    text = text.replace("[", "")
    text = text.replace("]", "")
    text = re.sub(r'<sup style="font-size:60%"> \d+\) </sup>', "", text)

    while text.find("  ") > -1:
        text = text.replace("  ", " ")

    text = text.replace(" ,", ",")
    text = text.replace(" .", ".")

    return text


def next_footnote_sup(elem, cursor):
    """
    Returns the next footnote number in the given element. Sometimes the
    number is located in the next element, for example: "or not the
    [minister]. <sup ...> 2) </sup>". In these cases we'll need to peek into
    the next element. We'll do this by changing the haystack in which we look.
    We won't use the cursor when looking for it though, because it will
    definitely be the first <sup> we run into, inside the next element.

    By the way:
        len('<sup style="font-size:60%">') == 27
    """
    if elem.text.find('<sup style="font-size:60%">', cursor) > -1:
        haystack = elem.text
        num_start = haystack.find('<sup style="font-size:60%">', cursor) + 27
        num_end = haystack.find("</sup>", cursor)
        num_text = haystack[num_start:num_end]
        num = num_text.strip().strip(")")
    else:
        # This means that the number was not found and typically happens when
        # a single "…" character is found. The reason that it's found without
        # indicating deletion are not entirely known, it appears to indicate
        # an unknown segment of text, i.e. portions of text lost forever
        # without explanation or cause. In any case, we must conclude that
        # we're not dealing with a footnote. As a result, we return None and
        # ask the function's caller to react accordingly.
        num = None

    return num


def generate_ancestors(elem, parent):
    # Locations of markers in footnote XML are denoted as a list of tags,
    # whose name correspond to the tag name where the marker is to be located,
    # and whose value represents the target node's "nr" attribute.
    # Example:
    #
    # <art nr="5">
    #   <subart nr="1">
    #     <sen>[Notice the markers?]</sen>
    #   </subart>
    # </art>
    #
    # This will result in location XML in the footnote XML as such:
    #
    # <location>
    #   <art>5</art>
    #   <subart>1</subart>
    #   <sen>1</sen>
    # </location>
    #
    # To achieve this, we iterate through the ancestors of the node currently
    # being processed. For each ancestor that we find, we add to the location
    # XML.
    ancestors = []
    for ancestor in elem.iterancestors():
        # We don't need the root node in a list of ancestors. It's obvious
        # that any tag mentioned here is contained in the root node.
        if ancestor.tag == "law":
            break

        # Figure out what the 'nr' attribute would be, if it were defined.
        if "nr" in ancestor.attrib:
            ancestors.insert(0, E(ancestor.tag, ancestor.attrib["nr"]))
        else:
            ancestors.insert(0, E(ancestor.tag, str(order_among_siblings(ancestor))))

        if ancestor == parent:
            # We're not interested in anything
            # beyond the parent node.
            break

    # If we cannot find a 'nr' attribute, we'll figure it out and still put it in.
    if "nr" in elem.attrib:
        ancestors.append(E(elem.tag, str(elem.attrib["nr"])))
    else:
        ancestors.append(E(elem.tag, str(order_among_siblings(elem))))

    return ancestors


# Examines the often mysterious issue of whether we're dealing with a new
# chapter or not. There is quite a bit of ambiguity possible so this question
# needs to be dealt with in more than a one-liner, both for flow and code
# clarity.
def check_chapter(lines, law):
    # We assume that chapters always start in bold.
    if lines.peek(0).strip() != "<b>":
        return ""

    matcher = Matcher()

    # Short-hand.
    peek_stripped = strip_markers(lines.peek()).strip()

    line_type = ""

    # If the line matches "fylgiskj[aö]l", it indicates that we've run into
    # accompanying documents that are not a part of the legal text itself. We
    # are unable to predict their format and parsing them will always remain
    # error-prone when possible to begin with. Possibly we'll include them as
    # raw HTML goo later.
    if matcher.check(peek_stripped.lower(), "fylgiskj[aö]l"):
        line_type = "extra-docs"

    # Same goes for appendices as extra-docs.
    elif matcher.check(peek_stripped.lower(), ".* viðauki"):
        line_type = "appendix"

    # We'll assume that temporary clauses are always in a chapter and never in
    # a subchapter. This has not been researched.
    elif peek_stripped.lower().find("bráðabirgð") > -1:
        line_type = "chapter"

    # Check if this is an "article chapter". Those are not exactly numerical
    # articles, but chapter-like phenomena that resides inside articles, or
    # even their subarticles.
    #
    # FIXME: This should actually be implemented alongside the Roman-parsing
    # elow. For now, we avoid mixing up Roman numerals with Latin letters by
    # only considering the letters A-H here as potential article chapters.
    elif (
        len(peek_stripped) > 1
        and peek_stripped[1] == "."
        and peek_stripped[0] in string.ascii_uppercase[0:8]
    ):
        line_type = "art-chapter"

    else:
        # We must examine the first "sentence" to see if it constitute a Roman
        # numeral. Possibly we'll analyze it better later to determine things
        # like subchapters.
        first = peek_stripped[0 : peek_stripped.find(".")]

        # If f.e. ". kafli" or ". hluti" can be found...
        if any(
            [peek_stripped.find(". %s" % w) > -1 for w in ["kafli", "hluti", "bók"]]
        ):
            line_type = "chapter"
        # We exclude "C" and "D" because as Roman numerals, they are much too
        # high to ever be used for a chapter. Later we may need to revise this
        # when we implement for support chapters/subchapters organized by
        # Latin letters. But since we don't support it yet, we'll just ignore
        # them like we do "A" and "B".
        elif is_roman(first) and first not in ["C", "D"]:
            line_type = "chapter"

    # If we've reached this point without conclusion, this is an ambiguous
    # bold section that are (as of yet) unable to determine the nature of.
    # This occurs in 96. gr. laga nr. 55/1991, for example.
    if line_type == "":
        line_type = "ambiguous"

    return line_type


# A function for intelligently splitting textual content into separate
# sentences based on linguistic rules and patterns.
def separate_sentences(content):
    # Contains the resulting list of sentences.
    sens = []

    # This weirdness only occurs in 88/1991 (@151c). We would like to replace
    # "&nbsp;" with a regular space here, because if we do it during initial
    # cleaning of original HTML, we will lose syntactic information that
    # "&nbsp;" may provide, required for planned improvements in parsing.
    # However, when the code arrives here, the "&nbsp;"s in the text have
    # turned into "\xa0", so we'll be replacing that instead. (Also, doing
    # this here instead of during initial cleaning seems to have fixed a bug
    # in some range markers, where the spaces were creeping in.)
    content = content.replace("\xa0\xa0\xa0\xa0\xa0", " ")

    # Reference shorthands are strings that are used in references. They are
    # often combined to designate a particular location in legal text, for
    # example "7. tölul. 2. mgr. 5. gr.", meaning numerical article 7 in
    # subarticle 2 of article 5. Their use results in various combinations of
    # numbers and dots that need to be taken into account to avoid wrongly
    # starting a new sentence when they are encountered.
    reference_shorthands = ["gr", "mgr", "málsl", "tölul", "staf"]

    # Encode recognized short-hands in text so that the dots in them don't get
    # confused for an end of a sentence. They will be decoded when appended to
    # the resulting list.
    #
    # Note that whether there should be a dot at the end of these depends on
    # how they are typically used in text. Any of these that might be used at
    # the end of a sentence should preferably not have a dot at the end. Those
    # that are very unlikely to be used at the end of a sentence should
    # however and with a dot.
    #
    # This is because there is an ambiguity after one of these is used, if the
    # following letter is a capital letter, because the capital letter may
    # indicate either the start of a new sentence, OR it could just be the
    # name of something, since names start with capital letters. This is why
    # "a.m.k." and "þ.m.t." end with dots, because they very well have a
    # capitalized name after them but are very unlikely to be used at the end
    # of a sentence, while "o.fl." is extremely unlikely to be followed by a
    # name, but may very well end a sentence.
    recognized_shorts = [
        "A.m.k.",
        "t.d.",
        "þ.m.t.",
        "sbr.",
        "nr.",
        "skv.",
        "m.a.",
        "a.m.k.",
        "þ.e.",
        "o.fl",
        "þ.m",
        "f.h.",
        "o.þ.h.",
    ]
    for r in recognized_shorts:
        content = content.replace(r, r.replace(".", "[DOT]"))

    # Certain things, like HTML tables (<table>) and links (<a>) should never
    # be split into separate sentence. We'll run through those tags and encode
    # every dot within them.
    non_splittable_tags = ["table", "a"]
    for nst in non_splittable_tags:
        cursor = 0

        # Location of the start tag.
        html_loc = content.find("<%s" % nst, cursor)

        while html_loc > -1:
            # Location of the end tag.
            html_end_loc = content.find("</%s>" % nst, cursor) + len("</%s>" % nst)

            # Fish out the tag contnet.
            tag_content = content[html_loc:html_end_loc]

            # Encode the dots in the tag content.
            tag_content = tag_content.replace(".", "[DOT]")

            # Stitch the encoded tag content back into the content.
            content = content[:html_loc] + tag_content + content[html_end_loc:]

            # Continue to see if we find more non-splittable tags.
            cursor = html_loc + 1
            html_loc = content.find("<%s" % nst, cursor)

            del html_end_loc
            del tag_content
        del cursor
        del html_loc
    del non_splittable_tags

    # The collected sentence so far. Chunks are appended to this string until
    # a new sentence is determined to be appropriate. Starts empty and and is
    # reset for every new sentence.
    collected = ""

    # We'll default to splitting chunks by dots. As we iterate through the
    # chunks, we will determine the cases where we actually don't want to
    # start a new sentence.
    chunks = super_iter(content.split("."))

    for chunk in chunks:
        # There is usually a period at the end and therefore a trailing, empty
        # chunk that we're not interested in.
        if chunk == "":
            continue

        # Start a new sentence by default. We'll only continue to gather the
        # chunks into the collected sentence when we find a reason to, but
        # normally a dot means an end of a sentence, thus a new one.
        split = True

        # Collect the chunk into the sentence so far. If we decide not to
        # start a new sentence, then this variable will grow until we decide
        # to, at which point it's added to the result and cleared.
        collected += chunk

        # Previews the next chunk before it is processed itself, so that we
        # can determine the context in both directions.
        next_chunk = chunks.peek()

        if next_chunk is not None:
            # We need to strip markers from the next chunk, because various
            # symbols may get in the way of us accurately figuring out how the
            # next chunk starts.
            next_chunk = strip_markers(next_chunk)

            # Don't start a new sentence if the first character in the next
            # chunk is lowercase.
            if len(next_chunk) > 1 and next_chunk[0] == " " and next_chunk[1].islower():
                split = False

            # Don't start a new sentence if the character immediately
            # following the dot is a symbol indicating that the sentence's end
            # has not yet been reached (comma, semicomma etc.).
            if len(next_chunk) > 0 and next_chunk[0] in [
                ",",
                ";",
                "–",
                "-",
                "[",
                "]",
                "…",
            ]:
                split = False

            # Don't start a new sentence if the dot is a part of a number.
            if len(next_chunk) > 0 and next_chunk[0].isdigit():
                split = False

            # Don't split if dealing with a reference to an article,
            # sub-article, numerical article or whatever.
            # Example:
            #    3. mgr. 4. tölul. 1. gr.
            last_word = chunk[chunk.rfind(" ") + 1 :]
            if last_word in reference_shorthands:
                next_chunk2 = chunks.peek(2)
                if (
                    next_chunk.strip().isdigit()
                    and next_chunk2.strip() in reference_shorthands
                ):
                    split = False

                # Support for referencing things like:
                #     3. tölul. C-liðar 7. gr.
                if re.match("^ [A-Z]-lið", next_chunk) is not None:
                    split = False

        # Add the dot that we dropped when splitting.
        collected += "."

        if split:
            # Decode the "[DOT]"s back into normal dots.
            collected = collected.replace("[DOT]", ".")

            # Append the collected sentence.
            sens.append(collected.strip())

            # Reset the collected sentence.
            collected = ""

    # Since we needed to drop the dot when splitting, we needed to add it
    # again to every chunk. Sometimes the content in its entirety doesn't end
    # with a dot though, but rather a comma or colon or some such symbol. In
    # these cases we have wrongly added it to the final chunk after the split,
    # and so we'll just remove it here. This could probably be done somewhere
    # inside the loop, but it would probably just be less readable.
    if content and content[-1] != "." and sens[-1][-1] == ".":
        sens[-1] = sens[-1].strip(".")

    # Make sure that tables always live in their own sentence.
    new_sens = []
    for sen in sens:
        # Note: We don't check if the table is in the beginning, because if it
        # is, it already lives in its own sentence. We're only interested in
        # it if it's inside the sentence but not at the beginning.
        table_loc = sen.find("<table ")
        if table_loc > 0:
            # Quite likely, there's a space between the table and the
            # preceding text, which we strip away.
            new_sens.append(sen[:table_loc].strip())
            new_sens.append(sen[table_loc:])
        else:
            new_sens.append(sen)
    sens = new_sens

    #########################################################################
    # Consider the following texts in law nr. 33/1944.
    #
    # Case 1:
    #
    # "...og skulu þá forsætisráðherra, forseti … 1) Alþingis og forseti..."
    #
    # Case 2:
    #
    # "...hlotið fylgi 3/4 hluta þingmanna … 1) Þjóðaratkvæðagreiðslan skal
    # þá..."
    #
    # In the former example, the deletion marker simply indicates the deletion
    # of content in the middle of a sentence. In the latter example, the
    # deletion has taken place at the end of a prior sentence which is still
    # followed by a new sentence, but without a period.
    #
    # This is a design choice in the official HTML that creates ambiguity when
    # a deletion marker is found in the middle of a sentence followed by a
    # capitalized word. The problem is that human knowledge is required to
    # determine the difference between a word that is capitalized because it's
    # a name ("Alþingi") versus a word that is capitalized because it's
    # starting a new sentence ("Þjóðaratkvæðagreiðslan").
    #
    # To combat this, we'll iterate through sentences that contain a deletion
    # marker and check for basic things like whether the marker is followed by
    # a capitalized word.
    #
    # The user is then asked whether the deletion marker also indicates a new
    # sentence. The choice of the user is then recorded in a file called
    # "splitmap.json" for future reference. In future iterations, that file
    # will first be checked, so that we never ask the user twice. This way, a
    # map of splits ("splitmap") is built up over time as we run into more of
    # these instances and receive answers from the user as we go.
    #########################################################################

    # Determines whether a provided text is likely to start a new sentence
    # given what we know from "splitmap.json", asking the user if the answer
    # cannot be found there.
    def check_sentence_start(pre_text, post_text):
        # We're not interested in markers, only content.
        pre_text = strip_markers(pre_text).strip()
        post_text = strip_markers(post_text).strip()

        # Find the first word, if one exists.
        next_post_word = post_text[0 : post_text.find(" ")]

        # Empty string does not count as a sentence.
        if not next_post_word:
            return False

        # Sentence must start with the first word capitalized.
        if not next_post_word[0].isalpha() or not next_post_word[0].isupper():
            return False

        # The "splitmap" keeps a record of which combinations of pre_text and
        # post_text classify as split (two sentences) or unsplit (two
        # sentences). Here we read the splitmap to check the current text.
        with open(SPLITMAP_FILENAME, "r") as f:
            splitmap = json.load(f)

        # This is the variable that will be stored in "splitmap.json". It's
        # worth noting why this format is chosen instead of an MD5 sum, for
        # example. One design goal is for "splitmap.json" to be easily
        # searchable by a human in case the wrong selection is made at some
        # point. The "[MAYBE-SPLIT]" string is used instead of a period or
        # some other symbol for readability reasons as well.
        combined_text = pre_text + "[MAYBE-SPLIT]" + post_text

        if combined_text in splitmap:
            return splitmap[combined_text]

        # If the string cannot be found in the splitmap, we'll need to ask the
        # user. We'll then record that decision for future reference.
        width, height = terminal_width_and_height()
        print()
        print("-" * width)
        print("Ambiguity found in determining the possible end of a sentence.")
        print()
        print("Former chunk: %s" % pre_text)
        print()
        print("Latter chunk: %s" % post_text)
        print()
        answer = input("Do these two chunks of text constitute 1 sentence or 2? [1/2] ")
        while answer not in ["1", "2"]:
            answer = input("Please select either 1 or 2: ")

        # If the user determines that the text is composed of two sentences,
        # it means that the text should be split (True).
        split = True if answer == "2" else False

        # Write the answer.
        splitmap[combined_text] = split
        with open(SPLITMAP_FILENAME, "w") as f:
            json.dump(splitmap, f)

        return split

    # Iterate the sentences, find deletion markers, and split by need.
    new_sens = []
    for sen in sens:
        cursor = 0
        deletion_found = sen.find("…", cursor)
        while deletion_found > -1:
            # Check if there's content before the marker. If not, then we
            # don't want to split, because then it belongs at the beginning of
            # the next sentence instead of having an entire sentence just for
            # the marker.
            before = len(strip_markers(sen[0:deletion_found]).strip()) > 0

            if before and check_sentence_start(
                sen[0:deletion_found], sen[deletion_found:]
            ):
                # At this point, we've determined that the deletion marker
                # starts a new sentence.

                # Add the missing period, the lack of which is the source of
                # the problem we're solving here. It may seem like a weird
                # place to put it, between the deletion marker and the
                # superscript, but this is in fact where commas are placed
                # when deletions occur immediately before them. In other
                # words, we'll want periods to act like commas.
                sen = sen[0 : deletion_found + 1] + "." + sen[deletion_found + 2 :]

                # Find the location where we want to split, which is
                # immediately following the deletion marker's next closing
                # superscript tag. BTW: len('</sup>') == 6
                split_loc = sen.find("</sup>", deletion_found + 1) + 6

                # Mark the place in the sentence where we intend to split.
                # We'll also add a period to denote the end of the sentence in
                # the text; the lack of which is responsible for us having to
                # perform this peculiar operation.
                sen = sen[0:split_loc] + "[SPLIT]" + sen[split_loc + 1 :]

            cursor = deletion_found + 1
            deletion_found = sen.find("…", cursor)

        new_sens.extend(sen.split("[SPLIT]"))
    sens = new_sens

    return sens


def add_sentences(target_node, sens):
    """
    Gracefully adds a bunch of sentences to a target node, but also considering
    the sentences that are already there before and may need specifying as
    belonging to different sub-paragraphs.

    NOTE:
    The original version of this function enclosed the provided sentences in a
    paragraph, unless the target node was already a paragraph, and then
    returned that paragraph. We have disbanded the use of paragraphs (at least
    for now) due to difficulties they introduce in creating a WYSIWYG editor.
    Instead, what was previously expressed using specific `<paragraph>` tags
    is now expressed in attributes of the `sen` elements created by this
    function. This is hopefully enough for other software to make sense of the
    nature of the text when formatting and referencing.
    """

    # There may be already existing sentences in the element we're adding to.
    # This happens when a new sentence actually denotes a new sub-paragraph.
    # However, since our format does not contain sub-paragraphs (due to
    # limitations it places on a visual editor), we will instead represent
    # this information in attributes.
    sub_par_nr = 1
    prior_sens = target_node.findall("sen")
    prior_sens_count = len(prior_sens)

    # Figure out if these sentences are in a new sub-paragraph.
    if prior_sens_count > 0:
        last_sen = prior_sens[-1]
        if "sub-paragraph-nr" in last_sen.attrib:
            sub_par_nr = int(last_sen.attrib["sub-paragraph-nr"]) + 1
        else:
            sub_par_nr = 2

    # Append sentences to element and automatically configure them.
    sen_nr = 0
    for sen in sens:
        sen_nr += 1

        sen_elem = E.sen(sen, nr=str(sen_nr))

        # Special flag to assist visual software, indicating that even though
        # this is a new sentence in the file, it visually represents a new
        # sub-paragraph.
        if sen_nr == 1 and sub_par_nr > 1:
            sen_elem.attrib["ultimate-nr"] = str(prior_sens_count + sen_nr)
            sen_elem.attrib["sub-paragraph-nr"] = str(sub_par_nr)
            sen_elem.attrib["new-sub-paragraph"] = "true"

        target_node.append(sen_elem)
