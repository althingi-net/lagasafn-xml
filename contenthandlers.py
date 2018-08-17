from utils import strip_markers
from utils import super_iter

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

    return sens
