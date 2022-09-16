import json
import os
import re
import roman
import settings
import subprocess

STRAYTEXTMAP_FILENAME = os.path.join('data', 'json-maps', 'straytextmap.json')


class UnexpectedClosingBracketException(Exception):
    def __str__(self):

        # We'll try to figure out enough information for the user to be able
        # to locate it in the legal text, so that the problem can be examined,
        # the law manually patched and Parliament notified about the error.

        try:
            node = self.args[0]
        except IndexError:
            return Exception('LegalFormatException expects an argument')

        # Work our way up the node hierarchy to construct a list describing
        # the problem node's lineage.
        trail = [node]
        parent = node.getparent()
        while parent.tag != 'law':
            trail.insert(0, parent)
            parent = parent.getparent()

        # Construct the error message shown when the Exception is thrown.
        msg = 'Unexpected closing bracket. Location: '
        for i, node in enumerate(trail):

            # Show arrow between parent/child relationships.
            if i > 0:
                msg += ' -> '

            # Construct tag description.
            msg += '[%s' % node.tag
            if 'nr' in node.attrib:
                msg += ':%s' % node.attrib['nr']
            msg += ']'

        # Append the actual text containing the problem.
        msg += ', in input text "%s"' % node.text

        return msg


# Returns a list of law_ids sorted first by the year ("2020" in "123/2020") as
# the first key, and the legal number as the second key ("123" in "123/2020").
# Law number typecasted to integer to get canonical order.
def sorted_law(law_ids):
    return list(reversed(
        sorted(
            law_ids,
            key=lambda law_id: (
                law_id[law_id.find('/')+1:],
                int(law_id[:law_id.find('/')])
            )
        )
    ))


def create_url(law_num, law_year):
    '''
    Creates a URL to Alþingi's website from a law_num and law_year. Used for
    development, so don't remove it, even if it's nowhere used in the code.
    '''
    fixed_width_law_num = str(law_num)
    while len(fixed_width_law_num) < 3:
        fixed_width_law_num = '0%s' % fixed_width_law_num

    base_url = 'https://www.althingi.is/lagas/%s/%s%s.html'
    return base_url % (
        settings.CURRENT_PARLIAMENT_VERSION,
        law_year,
        fixed_width_law_num
    )


def numart_next_nrs(prev_numart):
    '''
    Returns a list of expected next numbers from the given prev_numart. For
    example, if the prev_numart's number is "1", then "2" and "1a" are
    expected. If it's "b", then "c" is expected.
    '''

    matcher = Matcher()

    prev_numart_nr = prev_numart.attrib['nr']
    expected_numart_nrs = []
    if prev_numart.attrib['type'] == 'numeric':
        if prev_numart_nr.isdigit():
            # If the whole thing is numerical, we may expect either the next
            # numerical number (i.e. a 10 after a 9), or a numart with a
            # numerical and alphabetic component (i.e. 9a following a 9).
            expected_numart_nrs = [
                str(int(prev_numart_nr) + 1),
                str(int(prev_numart_nr)) + 'a',
            ]

        elif matcher.check(prev_numart_nr, r'(\d+)-(\d+)'):
            # Numarts may be ranges, (see 145. gr. laga nr. 108/2007), in
            # which case we only need to concern ourselves with the latter
            # number to determine the expected values.

            from_numart_nr, to_numart_nr = matcher.result()

            expected_numart_nrs = [
                str(int(to_numart_nr) + 1),
                str(int(to_numart_nr)) + 'a',
            ]

        else:
            # If at this point the whole thing starts with a number but is not
            # entirely a number, it means that the numart is a mixture of both
            # (f.e. 9a). In these cases we'll expect either the next number
            # (10 following 9a) or the same number with the next alphabetic
            # character (9b following 9a).
            alpha_component = prev_numart_nr.strip('0123456789')
            num_component = int(prev_numart_nr.replace(alpha_component, ''))

            expected_numart_nrs = [
                str(num_component + 1),
                str(num_component) + chr(int(ord(alpha_component)) + 1),
            ]

    elif prev_numart.attrib['type'] == 'en-dash':
        expected_numart_nrs += ['—', '–']
    elif prev_numart.attrib['type'] == 'roman':
        new_roman = roman.toRoman(roman.fromRoman(prev_numart_nr.upper()) + 1)
        if prev_numart_nr.islower():
            new_roman = new_roman.lower()

        expected_numart_nrs.append(new_roman)
    else:
        # Check if an alphabetic numart is surrounded by "(" and ")". Only
        # known to happen in 19/1996, which seems to be, in fact, an
        # international agreement and not a law.
        if prev_numart_nr[0] == '(' and prev_numart_nr[-1] == ')':
            numart_to_increment = prev_numart_nr[1:-1]
            next_numart_nr = '(%s)' % chr(int(ord(numart_to_increment)) + 1)
            expected_numart_nrs.append(next_numart_nr)

        elif prev_numart_nr == 'ö':

            # After the last character of the Icelandic alphabet, "ö", the
            # numart can be continued by using two letters, "aa", "ab", "ac"
            # and so forth. This is hard-coded for now but should be
            # implemented logically at some point.
            #
            # TODO: Implement this logic logically instead of hard-coding.

            expected_numart_nrs = ['aa']

        elif prev_numart_nr == 'aa':

            # Presumably by mistake, in 43. gr. laga nr. 55/2009, the numart
            # "aa" is followed by "bb" instead of "ab".
            #
            # TODO: Check if this is still needed if version 150b of the law
            # is obsolete. Althingi was notified of the mistake during that
            # parliament, and may have fixed it.
            #
            # Even greater madness exists in 8. gr. laga nr. 51/2016, although
            # that apparent mistake is also in the bill that became the law,
            # and so won't be fixed without a bill being passed in Parliament.
            # I **guess** this is the right way to deal with it. Maybe I'm
            # wrong and the proper method is just to double the length of the
            # same string with the same letter.

            expected_numart_nrs = ['ab', 'bb']
        elif prev_numart_nr == 'bb':
            expected_numart_nrs = ['bc', 'cc']
        elif prev_numart_nr == 'cc':
            expected_numart_nrs = ['cd', 'dd']
        elif prev_numart_nr == 'dd':
            expected_numart_nrs = ['de', 'ee']
        elif prev_numart_nr == 'ee':
            expected_numart_nrs = ['ef', 'ff']

        else:
            expected_numart_nrs.append(chr(int(ord(prev_numart_nr)) + 1))

    return expected_numart_nrs


def determine_month(month_string):
    '''
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
    '''

    # We know of one instance where the year gets re-added at the end, in
    # version 148c. We'll deal with this by replacing that known string with
    # the month's name only. When the data gets fixed, this line can be
    # removed, but will still be harmless. -2019-01-02
    # String: 2003 nr. 7 11. febrúar 2003
    # UR: https://www.althingi.is/lagas/nuna/2003007.html
    month_string = month_string.replace('febrúar 2003', 'febrúar')

    months = [
        'janúar',
        'febrúar',
        'mars',
        'apríl',
        'maí',
        'júní',
        'júlí',
        'ágúst',
        'september',
        'október',
        'nóvember',
        'desember',
    ]

    return months.index(month_string) + 1


def is_roman(goo):
    try:
        roman.fromRoman(goo)
        result = True
    except roman.InvalidRomanNumeralError:
        result = False

    return result


def terminal_width_and_height():
    height, width = [int(v) for v in subprocess.check_output(['stty', 'size']).split()]
    return width, height


def strip_links(text):
    '''
    Strips links from text. Also strips trailing whitespace after the link,
    because there is always a newline and a tab after the links in our input.
    '''

    # There is an occasional link that we would like to preserve. So far, they
    # can identified by their content containing the special character "…",
    # which means that the link is in fact a comment. Instead of stripping
    # these from the HTML, we'll leave them alone and post-process them into
    # proper XML in the main processing function. Note that for the time
    # being, they are left as HTML-encoded text and not actual XML (until the
    # aforementioned XML post-processing takes place).

    regex = r'<a [^>]*?>\s*([^…]*?)\s*</a>\s*'
    text = re.sub(regex, r'\1', text)

    return text


def order_among_siblings(elem):
    '''
    Returns the order of the given element among its siblings. For example, if
    there are three <doodoo> elements in a row, and you call this function
    with the second one, it will return 2.
    '''

    result = None

    for i, sibling in enumerate(elem.getparent().findall(elem.tag)):
        if sibling == elem:
            result = i + 1
            break

    return result


def xml_lists_identical(one, two):
    '''
    Takes two lists of XML nodes and checks whether they have the same
    tagnames, texts (values) and attributes. Does not check subnodes.
    '''

    if type(one) is not list or type(two) is not list:
        raise TypeError('xml_lists_identical takes exactly two lists')

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
    '''
    Takes an XML node and returns its URL, or the closest thing we have.
    There is a certain limit to how precise we want to make the URL, both
    because it's not necessarily useful for the user to go deeper than into
    the relevant article, but also because with numarts and such, the anchors
    in the HTML tend to become both unreliable and unpredictable.
    '''
    article_nr = None

    node = input_node
    while node.tag != 'law':
        if node.tag == 'art':
            # If the article is denoted in Roman numerals, it will be upper-case in the URL.
            article_nr = node.attrib['nr'].upper()

        node = node.getparent()

    #########################################################
    # At this point, `node` will be the top-most `law` tag. #
    #########################################################

    # Make sure that the law number is always exactly three digits.
    law_nr = str(node.attrib['nr'])
    while len(law_nr) < 3:
        law_nr = '0%s' % law_nr

    url = 'https://www.althingi.is/lagas/%s/%s%s.html#G%s' % (
        settings.CURRENT_PARLIAMENT_VERSION,
        node.attrib['year'],
        law_nr,
        article_nr
    )

    return url


def generate_legal_reference(input_node, skip_law=False):
    '''
    Takes an XML node and returns a string representing the formal way of
    referring to the same location in the legal codex.
    '''
    result = ''
    node = input_node
    matcher = Matcher()

    # If we're given the top-most node, which refers to the law itself, then
    # we'll return the legal reference to the law itself (in the nominative
    # case), regardless of whether `skip_law` was true or not, since
    # otherwise we return nothing and that's not useful.
    if node.tag == 'law':
        return 'lög nr. %s/%s' % (node.attrib['nr'], node.attrib['year'])

    while node.tag != 'law':
        if node.tag == 'numart':
            if node.attrib['type'] == 'alphabet':
                result += '%s-stafl. ' % node.attrib['nr']
            elif node.attrib['type'] in ['numeric', 'roman']:
                result += '%s. tölul. ' % node.attrib['nr']
            elif node.attrib['type'] == 'en-dash':
                result += '%s. pkt. ' % node.attrib['nr']
            else:
                raise Exception('Parsing of node not implemented')
        elif node.tag == 'subart':
            result += '%s. málsgr. ' % node.attrib['nr']
        elif node.tag == 'art':
            if node.attrib['nr'].isdigit():
                result += '%s. gr. ' % node.attrib['nr']
            else:
                if matcher.check(node.attrib['nr'], r'(\d+)(.+)'):
                    matches = matcher.result()
                    result += '%s. gr. %s ' % (matches[0], matches[1])
                else:
                    raise Exception('Parsing of node not implemented')
        elif node.tag == 'chapter':
            pass
        else:
            raise Exception('Parsing of node not implemented')

        node = node.getparent()

    #########################################################
    # At this point, `node` will be the top-most `law` tag. #
    #########################################################

    # Add the reference to the law if requested.
    if not skip_law:
        result += 'laga nr. %s/%s' % (node.attrib['nr'], node.attrib['year'])

    return result


# We are given some extra sentences, that we don't know where to locate
# because it cannot be determined by the input text alone.
def ask_user_about_location(extra_sens, numart):
    legal_reference = generate_legal_reference(numart, skip_law=True)
    url = generate_url(numart)

    # Calculated values that we'll have to use more than once.
    joined_extra_sens = ' '.join(extra_sens)
    numart_xpath = numart.getroottree().getpath(numart)
    law = numart.getroottree().getroot()

    # Open the straytext map.
    with open(STRAYTEXTMAP_FILENAME, 'r') as f:
        straytextmap = json.load(f)

    # Construct the straytext map key. It must be quite detailed because we
    # may have multiple instances of the same text, even in the same document.
    straytextmap_key = '%s/%s:%s:%s' % (
        law.attrib['nr'],
        law.attrib['year'],
        numart_xpath,
        joined_extra_sens
    )

    # Check if the straytext map already has our answer.
    if '--rebuild-straytextmap' not in settings.options and straytextmap_key in straytextmap:
        # Okay, we have an entry for this text.
        entry = straytextmap[straytextmap_key]

        # Check if the purported XPath destination fits with the legal
        # reference. If so, we can be confident that the location is correct,
        # even if the law has changed somewhat. This will break if the text
        # gets moved about, but then the user will simply be asked again.
        destination_node = law.xpath(entry['xpath'])[0]
        if generate_legal_reference(destination_node, skip_law=True) == entry['legal_reference']:
            return destination_node

    # Figure out the possible locations to which the text might belong.
    possible_locations = []
    node = numart
    while node.getparent().tag != 'law':
        possible_locations.append(node)
        node = node.getparent()

    # Add the law itself as a possible location. Extremely rare, but happens
    # for example in "forsetaúrskurður" nr. 105/2020
    # (https://www.althingi.is/lagas/151c/2020105.html).
    possible_locations.append(law)

    # Try to explain the situation to the user.
    width, height = terminal_width_and_height()
    print()
    print('-' * width)
    print('We have discovered the following text that we are unable to programmatically locate in the XML in:')
    print()
    print('Law: %s/%s' % (law.attrib['nr'], law.attrib['year']))
    print()
    print('It can be found in: %s' % legal_reference)
    print('Link: %s' % url)
    print()
    print('The text in question is:')
    print()
    print('"%s"' % joined_extra_sens)
    print()
    print('Please open the legal codex in the relevant location, and examine which legal reference is the containing element of this text.');
    print()
    print('The options are:')
    for i, possible_location in enumerate(possible_locations):
        print(' - %d: %s' % (i+1, generate_legal_reference(possible_location)))
    print()
    print(' - 0: Skip (use only when answer cannot be provided)')

    # Get the user to decide.
    response = None
    while response not in range(0, len(possible_locations)+1):
        try:
            response = int(input('Select appropriate option: '))
        except ValueError:
            # Ignore nonsensical answer and keep asking.
            pass

    # User opted to skip this one.
    if response == 0:
        return None

    # Determine the selected node and get its reference.
    selected_node = possible_locations[response-1]
    selected_node_legal_reference = generate_legal_reference(selected_node, skip_law=True)

    # Tell the user what they selected.
    print('Selected location: %s' % selected_node_legal_reference)

    # Write this down in our straytextmap for later consultation, using the
    # sentences as a key to location information.
    straytextmap[straytextmap_key] = {
        'xpath': selected_node.getroottree().getpath(selected_node),
        'legal_reference': selected_node_legal_reference,
    }
    with open(STRAYTEXTMAP_FILENAME, 'w') as f:
        json.dump(straytextmap, f)

    return selected_node


# A super-iterator for containing all sorts of extra functionality that we
# don't get with a regular Python iterator. Note that this thing is
# incompatible with yields and is NOT a subclass of `iter` (since that's not
# possible), but rather a class trying its best to masquerade as one.
class super_iter():
    def __init__(self, collection):
        self.collection = collection
        self.index = 0

    def __next__(self):
        try:
            result = self.collection[self.index]
            self.index += 1
        except IndexError:
            raise StopIteration
        return result

    def prev(self):
        self.index -= 1
        if self.index < 0:
            raise StopIteration
        return self.collection[self.index]

    def __iter__(self):
        return self

    # Peek into the next item of the iterator without advancing it. Works with
    # negative numbers to take a peek at previous items.
    def peek(self, number_of_lines=1):
        peek_index = self.index - 1 + number_of_lines
        if peek_index >= len(self.collection) or peek_index < 0:
            return None
        return self.collection[peek_index]


class Matcher():
    '''
    A helper class to be able to check if a regex matches in an if-statement,
    but then process the results in its body, if there's a match. This is
    essentially to make up for Python's (consciously decided) inability to
    assign values to variables inside if-statements. Note that a single
    instance of it is created and then used repeatedly.

    Usage:

    if matcher.check(line, r'<tag goo="(\d+)" splah="(\d+)">'):  # noqa
        goo, splah = matcher.result()
    '''

    match = None

    def check(self, line, test_string):
        self.match = re.match(test_string, line)
        return self.match is not None

    def result(self):
        return self.match.groups()
