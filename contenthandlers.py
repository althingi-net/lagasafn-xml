import re

from lxml.builder import E

from utils import order_among_siblings
from utils import super_iter

def regexify_markers(text):
    '''
    Replaces markers in given text with regex that will match those same
    markers. The point is to have a regex that will match the string both with
    and without markers.
    '''

    text = re.sub(
        r'\[ ?',
        r'(\[? ?)?',
        text
    )
    text = re.sub(
        r'\],? <sup style="font-size:60%"> ?\d+\) ?</sup>,? ?',
        r'(\],? <sup( style="font-size:60%")?> ?\d+\) ?</sup>)?,? ?',
        text
    )
    text = re.sub(
        r'… <sup style="font-size:60%"> ?\d+\) ?</sup>,? ?',
        r'(… <sup( style="font-size:60%")?> ?\d+\) ?</sup>)?,? ?',
        text
    )
    text = text.replace(' ,', r' ?,')

    return text


def strip_markers(text):
    '''
    Strips markers from text and cleans up resulting weirdness.
    '''

    text = text.replace('…', '')
    text = text.replace('[', '')
    text = text.replace(']', '')
    text = re.sub(r'<sup style="font-size:60%"> \d+\) </sup>', '', text)

    while text.find('  ') > -1:
        text = text.replace('  ', ' ')

    text = text.replace(' ,', ',')
    text = text.replace(' .', '.')

    return text


def next_footnote_sup(elem, cursor):
    '''
    Returns the next footnote number in the given element. Sometimes the
    number is located in the next element, for example: "or not the
    [minister]. <sup ...> 2) </sup>". In these cases we'll need to peek into
    the next element. We'll do this by changing the haystack in which we look.
    We won't use the cursor when looking for it though, because it will
    definitely be the first <sup> we run into, inside the next element.

    By the way:
        len('<sup style="font-size:60%">') == 27
    '''
    if elem.text.find('<sup style="font-size:60%">', cursor) > -1:
        haystack = elem.text
        num_start = haystack.find('<sup style="font-size:60%">', cursor) + 27
        num_end = haystack.find('</sup>', cursor)
        num_text = haystack[num_start:num_end]
        num = num_text.strip().strip(')')
    else:
        haystack = elem.getnext().text
        num_start = haystack.find('<sup style="font-size:60%">') + 27
        num_end = haystack.find('</sup>')
        num_text = haystack[num_start:num_end]
        num = num_text.strip().strip(')')

    return num


def generate_ancestors(elem, parent):
    # Locations of markers in footnote XML are denoted as a list of tags,
    # whose name correspond to the tag name where the marker is to be located,
    # and  whose value represents the target node's "nr" attribute.
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
        ancestors.insert(0, E(ancestor.tag, ancestor.attrib['nr']))
        if ancestor == parent:
            # We're not interested in anything
            # beyond the parent node.
            break

    # If we cannot find a 'nr' attribute, we'll figure it out and still put it in.
    if 'nr' in elem.attrib:
        ancestors.append(E(elem.tag))
    else:
        ancestors.append(E(elem.tag, str(order_among_siblings(elem))))

    return ancestors

# A function for intelligently splitting textual content into separate
# sentences based on linguistic rules and patterns.
def separate_sentences(content):

    # Contains the resulting list of sentences.
    sens = []

    # Reference shorthands are strings that are used in references. They are
    # often combined to designate a particular location in legal text, for
    # example "7. tölul. 2. mgr. 5. gr.", meaning numerical article 7 in
    # subarticle 2 of article 5. Their use results in various combinations of
    # numbers and dots that need to be taken into account to avoid wrongly
    # starting a new sentence when they are encountered.
    reference_shorthands = ['gr', 'mgr', 'málsl', 'tölul', 'staf']

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
        't.d.',
        'þ.m.t.',
        'sbr.',
        'nr.',
        'skv.',
        'm.a.',
        'a.m.k.',
        'þ.e.',
        'o.fl',
    ]
    for r in recognized_shorts:
        content = content.replace(r, r.replace('.', '[DOT]'))

    # HTML tables should never be split up into separate sentences, so we'll
    # encode every dot in them.
    cursor = 0
    html_loc = content.find('<table width="100%">', cursor)
    while html_loc > -1:
        html_end_loc = content.find('</table>', cursor) + len('</table>')

        # Fish out the HTML table.
        table_content = content[html_loc:html_end_loc]

        # Encode the dots in the HTML table.
        table_content = table_content.replace('.', '[DOT]')

        # Stitch the encoded table back into the content.
        content = content[:html_loc] + table_content + content[html_end_loc:]

        # Continue to see if we find more tables.
        cursor = html_loc + 1
        html_loc = content.find('<table width="100%">', cursor)
    del cursor
    del html_loc

    # The collected sentence so far. Chunks are appended to this string until
    # a new sentence is determined to be appropriate. Starts empty and and is
    # reset for every new sentence.
    collected = ''

    # We'll default to splitting chunks by dots. As we iterate through the
    # chunks, we will determine the cases where we actually don't want to
    # start a new sentence.
    chunks = super_iter(content.split('.'))

    for chunk in chunks:
        # There is usually a period at the end and therefore a trailing, empty
        # chunk that we're not interested in.
        if chunk == '':
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
            if len(next_chunk) > 1 and next_chunk[0] == ' ' and next_chunk[1].islower():
                split = False

            # Don't start a new sentence if the character immediately
            # following the dot is a symbol indicating that the sentence's end
            # has not yet been reached (comma, semicomma etc.).
            if len(next_chunk) > 0 and next_chunk[0] in [',', ';', '–', '-', '[', ']', '…']:
                split = False

            # Don't start a new sentence if the dot is a part of a number.
            if len(next_chunk) > 0 and next_chunk[0].isdigit():
                split = False

            # Don't split if dealing with a reference to an article,
            # sub-article, numerical article or whatever.
            # Example:
            #    3. mgr. 4. tölul. 1. gr.
            last_word = chunk[chunk.rfind(' ')+1:]
            if last_word in reference_shorthands:
                next_chunk2 = chunks.peek(2)
                if next_chunk.strip().isdigit() and next_chunk2.strip() in reference_shorthands:
                    split = False

        # Add the dot that we dropped when splitting.
        collected += '.'

        if split:
            # Decode the "[DOT]"s back into normal dots.
            collected = collected.replace('[DOT]', '.')

            # Append the collected sentence.
            sens.append(collected.strip())

            # Reset the collected sentence.
            collected = ''

    # Since we needed to drop the dot when splitting, we needed to add it
    # again to every chunk. Sometimes the content in its entirety doesn't end
    # with a dot though, but rather a comma or colon or some such symbol. In
    # these cases we have wrongly added it to the final chunk after the split,
    # and so we'll just remove it here. This could probably be done somewhere
    # inside the loop, but it would probably just be less readable.
    if content and content[-1] != '.' and sens[-1][-1] == '.':
        sens[-1] = sens[-1].strip('.')

    # Make sure that tables always live in their own sentence.
    new_sens = []
    for sen in sens:
        # Note: We don't check if the table is in the beginning, because if it
        # is, it already lives in its own sentence. We're only interested in
        # it if it's inside the sentence but not at the beginning.
        table_loc = sen.find('<table ')
        if table_loc > 0:
            # Quite likely, there's a space between the table and the
            # preceding text, which we strip away.
            new_sens.append(sen[:table_loc].strip())
            new_sens.append(sen[table_loc:])
        else:
            new_sens.append(sen)
    sens = new_sens

    #########################################################################
    # Consider the following texts in law nr. 33/1940.
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
    # marker followed by a capitalized word. We will try our best to determine
    # whether it's a name or the start of a new sentence, and if it's the
    # latter, we'll split the sentence, and otherwise we won't.
    #
    # This mechanism will almost certainly never be complete, but rather will
    # need to be updated as new ambiguous cases are discovered through the
    # processing of more and more law.
    #########################################################################

    # Determines whether a provided text is likely to start a new sentence
    # given what we know about occurrences in the legal text. This is
    # essentially a hack and is not reliable. As we process laws, with time we
    # will figure out characteristics of sentences that don't start new
    # sentences, presumably mostly by which words they start with, and we will
    # update this function to reflect that knowledge as it comes in.
    def probable_sentence_start(text):
        # We're not interested in markers, only content.
        text = strip_markers(text).strip()

        # Find the first word, if one exists.
        next_word = text[0:text.find(' ')]

        # Empty string does not count as a sentence.
        if not next_word:
            return False

        # Sentence must start with the first word capitalized.
        if not next_word[0].isalpha() or not next_word[0].isupper():
            return False

        # Words that we know never start new sentences. (Note: This is based
        # on Icelandic's grammar. We know that a sentence doesn't start with
        # "Alþingis" because it is in the genitive case.)
        if next_word in ['Alþingis']:
            return False

        # By default, provided texts are new sentences. If we haven't found a
        # reason to conclude that it is not, then we'll suggest that it
        # probably is.
        return True

    # Iterate the sentences, find deletion markers, and split by need.
    new_sens = []
    for sen in sens:
        cursor = 0
        deletion_found = sen.find('…', cursor)
        while deletion_found > -1:

            # Check if there's content before the marker. If not, then we
            # don't want to split, because then it belongs at the beginning of
            # the next sentence instead of having an entire sentence just for
            # the marker.
            before = len(strip_markers(sen[0:deletion_found]).strip()) > 0

            if before and probable_sentence_start(sen[deletion_found:]):
                # At this point, we've determined that the deletion marker
                # starts a new sentence.

                # Add the missing period, the lack of which is the source of
                # the problem we're solving here. It may seem like a weird
                # place to put it, between the deletion marker and the
                # superscript, but this is in fact where commas are placed
                # when deletions occur immediately before them. In other
                # words, we'll want periods to act like commas.
                sen = sen[0:deletion_found+1] + '.' + sen[deletion_found+2:]

                # Find the location where we want to split, which is
                # immediately following the deletion marker's next closing
                # superscript tag. BTW: len('</sup>') == 6
                split_loc = sen.find('</sup>', deletion_found+1) + 6

                # Mark the place in the sentence where we intend to split.
                # We'll also add a period to denote the end of the sentence in
                # the text; the lack of which is responsible for us having to
                # perform this peculiar operation.
                sen = sen[0:split_loc] + '[SPLIT]' + sen[split_loc+1:]

            cursor = deletion_found + 1
            deletion_found = sen.find('…', cursor)

        new_sens.extend(sen.split('[SPLIT]'))
    sens = new_sens

    return sens
