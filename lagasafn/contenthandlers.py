import json
import os
import re
import string

from lagasafn.utils import Matcher
from lagasafn.utils import is_roman
from lagasafn.utils import last_container_added
from lagasafn.utils import order_among_siblings
from lagasafn.utils import strip_links
from lagasafn.utils import super_iter
from lagasafn.utils import terminal_width_and_height
from lxml.builder import E

SPLITMAP_FILENAME = os.path.join("data", "json-maps", "splitmap.json")
MAGIC_EXPIRY_TOKEN = "MAGIC_94291_EXPIRY_TOKEN_A22922"


def is_numart_address(input):
    """
    Checks if the given string input is a legit numart address.

    It may be, for example:
    - 1.
    - 2.
    - 3.-4.
    - 5.–6.

    Note that those "–" and "-" are not the same symbol. Sometimes one is used
    and sometimes the other.
    """
    matcher = Matcher()
    return matcher.check(input.strip(), r"^\d+\.([-–]\d+\.)?$")


def get_nr_and_name(goo: str) -> (str, str):
    dot_loc = goo.find(".")
    if dot_loc > -1:
        nr = goo[:dot_loc]
        name = goo[dot_loc + 1 :].strip()
    elif is_numart_address(goo):
        nr = goo.strip()
        name = ""
    else:
        nr = ""
        name = goo.strip()

    return nr, name


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
    if len(question) and question[0] != "<" and not is_numart_address(question):
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
    text = text.replace("(", r"\(")
    text = text.replace(")", r"\)")

    # Opening markers.
    text = re.sub(r"\[( )?", r"(\[?\1?)?", text)

    # Closing markers, deletion markers and  pointers.
    # NOTE: The three backslashes before the closing parentheses is because
    # we must seek the string after it has been modified by the
    # parentheses-escaping code above. We're looking for "\)" instead of ")".
    # NOTE: We actually contain content from the given text in the new regex,
    # so that it doesn't over-match.
    matches = re.findall(r'((\.?) ?\[?\]?…?,?(\.?):? ?<sup style="font-size:60%"> ?(\d+)\\\) ?</sup>,? ?)', text)
    for match in matches:
        # The replacement string needs a little bit of adjusting depending on
        # the input, to a greater extent than possible with simple regex
        # replacements. For example, a "." is moved from a sentence like
        # "something." passed the closing marker if it exists, "something].".
        # Additional markers may be found around it, creating more somewhat
        # convoluted situations.
        replacement_string = ""
        if len(match[1]) or len(match[2]):  # Found a dot.
            # The dot can be found on either side of the "]", depending on
            # surroundings. We therefore need to have this optional "." if it
            # shows up on either side of the "]". Note that always including it,
            # without this condition, it breaks laws under certain conditions.
            #
            # NOTE: This optional dot is added to the front of the replacement
            # regex, despite being detected in two separate locations in the
            # input. This is because it is moved passed the closing marker
            # under certain conditions.
            replacement_string += r'\.?'
        replacement_string += r':? ?(\[?\]?…?,?\.?:? ?<sup( style="font-size:60%")?> ?' + match[3] + r'\) ?</sup>)?,? ?'

        text = text.replace(
            match[0],
            replacement_string
        )

    # Make stray deletion markers optional, i.e. those that aren't already.
    text = re.sub(r"…[^?]", r"(… ?)?", text)

    # FIXME: This is unexplained.
    text = text.replace(" ,", r" ?,")

    # Remove stray spaces.
    text = text.strip()

    return text


def strip_markers(text, strip_hellip_link=False):
    """
    Strips markers from text and cleans up resulting weirdness.

    By default, it leaves "…" alone when it's a link, but the
    `strip_hellip_link` parameter can be set to `True` for it to be included.
    """

    if not strip_hellip_link:
        # We want to keep "…" when it's a part of a link and is not a deletion
        # marker. We'll temporarily replace it with a piece of text that we'll
        # replace back later.
        text = text.replace("> … </a>", "> HELLIP </a>")

    # Remove change/deletion markers.
    text = text.replace("…", "")
    text = text.replace("[", "")
    text = text.replace("]", "")
    text = re.sub(r'<sup style="font-size:60%"> \d+\) </sup>', "", text)

    # Eliminate excessive whitespace.
    while text.find("  ") > -1:
        text = text.replace("  ", " ")

    text = text.replace(" ,", ",")
    text = text.replace(" .", ".")

    if not strip_hellip_link:
        # Re-insert the "…" that we saved from before.
        text = text.replace("> HELLIP </a>", "> … </a>")

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


def word_to_nr(input_word: str) -> str:
    """
    Turns cardinal numbers in text into Arabic numerals. Returns original if
    it's not a cardinal number.
    """
    word = input_word.lower()
    if word == "fyrsti":
        return "1"
    elif word == "annar":
        return "2"
    elif word == "þriðji":
        return "3"
    elif word == "fjórði":
        return "4"
    elif word == "fimmti":
        return "5"
    elif word == "sjötti":
        return "6"
    elif word == "sjöundi":
        return "7"
    elif word == "áttundi":
        return "8"
    elif word == "níundi":
        return "9"
    elif word == "tíundi":
        return "10"
    elif word == "ellefti":
        return "11"
    elif word == "tólfti":
        return "12"
    elif word == "þrettándi":
        return "13"
    elif word == "fjórtándi":
        return "14"
    elif word == "fimmtándi":
        return "15"
    else:
        return input_word


# Examines the often mysterious issue of whether we're dealing with a new
# chapter or not. There is quite a bit of ambiguity possible so this question
# needs to be dealt with in more than a one-liner, both for flow and code
# clarity.
def check_chapter(lines, law):
    # We assume that chapters always start in bold.
    if lines.peek(0).strip() != "<b>":
        return ""

    # Short-hand.
    peek_stripped = strip_markers(lines.peek()).strip()

    # We must examine the first "sentence" to see if it constitute a Roman
    # numeral. Possibly we'll analyze it better later to determine things
    # like subchapters.
    first = peek_stripped[0 : peek_stripped.find(".")]

    # First see if this is ignorable, because in that case we don't need to do
    # anything else.
    line_type = is_ignorable_chapter(peek_stripped)
    if len(line_type) > 0:
        return line_type

    # We'll assume that temporary clauses are always in a chapter and never in
    # a subchapter. This has not been researched.
    if peek_stripped.lower().find("bráðabirgð") > -1:
        line_type = "chapter"

    elif peek_stripped.lower().find("viðauki") > -1:
        line_type = "appendix"

    elif peek_stripped.lower().find("þáttur") > -1:
        line_type = "superchapter"

    # Check if this is an "article chapter". Those are not exactly numerical
    # articles, but chapter-like phenomena that resides inside articles, or
    # even their subarticles.
    #
    # FIXME: This should actually be implemented alongside the Roman-parsing
    # below. For now, we avoid mixing up Roman numerals with Latin letters by
    # only considering the letters A-H here as potential article chapters.
    elif (
        len(peek_stripped) > 1
        and peek_stripped[1] == "."
        and peek_stripped[0] in string.ascii_uppercase[0:8]
    ):
        if last_container_added(law).tag == "chapter":
            # We now know that this is a document with the format where
            # subchapters may be denoted as bold strings containing an A-H as
            # the `nr-title`. We'll mark the document as such for future
            # reference, because then these subchapters will keep popping
            # somewhere in the rest of the document.
            #
            # When this condition is never met, the same thing is considered
            # something else, for example an `art-chapter`.
            law.attrib["subchapter-bold-alphabet"] = "true"

        if (
            "subchapter-bold-alphabet" in law.attrib
            and law.attrib["subchapter-bold-alphabet"] == "true"
        ):
            # In codex version 153c, this is known to happen in:
            # - 75/1997
            # - 112/2008
            # - 45/2020
            line_type = "subchapter"
        else:
            line_type = "art-chapter"

    elif any(
        [peek_stripped.find(". %s" % w) > -1 for w in ["kafli", "hluti", "bók", "kap"]]
    ):
        # If f.e. ". kafli" or ". hluti" can be found...
        line_type = "chapter"
    elif peek_stripped.find(" kapítuli") > -1:
        line_type = "chapter"
    elif is_roman(first) and first not in ["C", "D"]:
        # We exclude "C" and "D" because as Roman numerals, they are much too
        # high to ever be used for a chapter. Later we may need to revise this
        # when we implement for support chapters/subchapters organized by
        # Latin letters. But since we don't support it yet, we'll just ignore
        # them like we do "A" and "B".
        line_type = "chapter"
    elif first.isdigit():
        # Check for what we'll call a `numart-chapter`, which is when the first
        # `numart` is bold.
        #
        # This is only known to occur in appendices, and currently the only
        # example is "I. viðauki laga nr. 7/1998.
        line_type = 'numart-chapter'
    elif law.getchildren()[-1].tag == "appendix":
        line_type = "appendix-chapter"
    elif lines.peek().strip()[-1] == ":":
        # These definitions are not chapters. They occur at least in 1. gr.
        # laga nr. 58/1998.
        line_type = "bold-definition"

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
    reference_shorthands = ["gr", "mgr", "málsl", "tölul", "staf", "viðauka"]

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
        "bls.",
        "kr.",
    ]
    for r in recognized_shorts:
        content = content.replace(r, r.replace(".", "{DOT}"))

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
            tag_content = tag_content.replace(".", "{DOT}")

            # Stitch the encoded tag content back into the content.
            content = content[:html_loc] + tag_content + content[html_end_loc:]

            # Continue to see if we find more non-splittable tags.
            html_loc = content.find("<%s" % nst, html_loc + 1)
            cursor = html_loc + 1

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
                    and (
                        next_chunk2.strip() in reference_shorthands
                        # Support for connecting words such as "1. tölul. 2. og
                        # 3. mgr." in 1. mgr. 3. gr. laga nr. 88/1991.
                        or next_chunk2.strip().split(" ")[0] in ["og", "eða"]
                    )
                ):
                    split = False

                # Support for referencing things like:
                #     3. tölul. C-liðar 7. gr.
                if re.match("^ [A-Z]-lið", next_chunk) is not None:
                    split = False

            # Add the dot that we dropped when splitting.
            collected += "."

        if split:
            # Decode the "{DOT}"s back into normal dots.
            collected = collected.replace("{DOT}", ".")

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
    #
    # NOTE: We check for both "." or the last character of "{DOT}" in `content`, because it could be either. We're assuming that "}" only being possible here due to the replacement of "." with "{DOT}" above.
    if content and content[-1] not in [".", "}"] and sens[-1][-1] == ".":
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
    deletion_offsets = []
    for sen in sens:
        cursor = 0
        deletion_found = sen.find("…", cursor)
        while deletion_found > -1:
            if sen.find("Hér hefur annaðhvort verið fellt brott") > -1:
                # Strip the <a href=...> but leave the text within.
                regex = r"<a [^>]*?>\s*(…)\s*</a>"
                sen = re.sub(regex, MAGIC_EXPIRY_TOKEN, sen)
                deletion_offsets.append(deletion_found)
                continue

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
    Gracefully adds a bunch of sentences to a target node, enclosing them in
    a paragraph. If the target node is itself a paragraph, the sentences get
    added to it, and the already existing paragraph returned instead.

    Returns the created/found paragraph for further use by caller.
    """

    if target_node.tag == "paragraph":
        # If target node is a paragraph, then the target and paragraph are
        # the same thing. This is to prevent paragraphs inside paragraphs when
        # a numart is contained within a paragraph, but also has text
        # following the numart. This happens in 18/2013, 132/2020 and 80/2022
        # in version 152c.
        paragraph = target_node
    else:
        # Construct paragraph, determining its number by examining how many
        # already exist in the target node.
        paragraph_nr = str(len(target_node.findall("paragraph")) + 1)
        paragraph = E("paragraph", {"nr": paragraph_nr})

        # Append paragraph to given node.
        target_node.append(paragraph)

    # Append sentences to paragraph, giving them numbers.
    sen_nr = 0
    for sen in sens:
        sen_nr += 1

        # Fish out definitions, denoted by being encompassed between `<i>` and
        # `</i>`. These must be re-styled by the rendering mechanism.
        definitions = None
        definitions_found = re.findall(r"<i>([^<]*)</i>", sen)
        if len(definitions_found) > 0:
            definitions = E("definitions")
            for definition_found in definitions_found:
                definitions.append(E("definition", definition_found.strip()))
                sen = sen.replace("<i>%s</i>" % definition_found, definition_found.strip())

        # Bold definitions are an anomaly in how definitions are presented.
        # Seems to happen only in 1. gr. laga nr. 58/1998 (153c).
        bold_definitions_found = re.findall(r"<b> ([^<]*:) </b>", sen)
        if len(bold_definitions_found) > 0:
            definitions = E("definitions")
            for definition_found in bold_definitions_found:
                definitions.append(E("definition", { "style": "bold" }, definition_found.strip()))
                sen = sen.replace("<b> %s </b>" % definition_found, definition_found.strip())

        sen_elem = E.sen(sen, nr=str(sen_nr))

        # Insert the definitions, if needed.
        if definitions is not None:
            paragraph.insert(0, definitions)

        expiry_loc = strip_markers(sen).strip().find(MAGIC_EXPIRY_TOKEN)
        if expiry_loc > -1:
            sen = sen.replace(MAGIC_EXPIRY_TOKEN, "…")
            sen_elem.text = sen
            # NOTE: In reality, the `expiry-symbol-offset` attribute only
            # prevents the node from being automatically deleted when it's
            # "empty" (i.e. empty if it's without markers).
            #
            # FIXME: It used to be the case that this was only used for
            # non-empty nodes to make sure they didn't get deleted, but is now
            # used to place the expiry symbol, at least in 1. mgr. 36. gr. laga
            # nr. 33/2013 (153c). This is inconvenient, because it doesn't
            # account for other markers in the rendering mechanism, and thus
            # the `expiry-symbol-offset` will only be correct when there are no
            # other markers in the same node. So far, this doesn't seem to be a
            # problem, but if more non-empty nodes with other markers start to
            # contain the expiry symbol in the future, then it probably needs
            # to be incorporated into the same mechanism that deals with
            # opening/closing/deletion/pointer markers with `words` and all, to
            # be resilient against them.
            sen_elem.attrib["expiry-symbol-offset"] = str(expiry_loc)

        paragraph.append(sen_elem)

    # Return paragraph, whether contructed or already existing.
    return paragraph


def is_ignorable_chapter(line: str) -> str:
    """
    Appendices and accompanying documents are sometimes appended to the law. We
    can't parse those, so we must ignore them. This function checks if the
    given line fulfills the criteria for such "ignorable" content.

    Returns the type of ignorable if ignorable, otherwise an empty string.
    """
    line_type = ""
    matcher = Matcher()

    # If the line matches "fylgiskj[aö]l", it indicates that we've run into
    # accompanying documents that are not a part of the legal text itself. We
    # are unable to predict their format and parsing them will always remain
    # error-prone when possible to begin with. Possibly we'll include them as
    # raw HTML goo later.
    if matcher.check(line.lower(), "fylgiskj[aö]l"):
        line_type = "extra-docs"

    return line_type


def remove_ignorables(soup):
    """
    Removes ignorables as defined by `is_ignorable_chapter`.
    """
    for b_tag in soup.find_all("b"):
        if is_ignorable_chapter(b_tag.text):
            to_be_extracted = b_tag

            while to_be_extracted:
                next_sibling = to_be_extracted.next_sibling
                to_be_extracted.extract()
                to_be_extracted = next_sibling
            break

    return soup
