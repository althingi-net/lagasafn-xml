import re
import roman
import subprocess

CURRENT_PARLIAMENT_VERSION = '151a'


def create_url(law_num, law_year):
    '''
    Creates a URL to Alþingi's website from a law_num and law_year. Used for
    development, so don't remove it, even if it's nowhere used in the code.
    '''
    fixed_width_law_num = str(law_num)
    while len(fixed_width_law_num) < 3:
        fixed_width_law_num = '0%s' % fixed_width_law_num

    base_url = 'https://www.althingi.is/lagas/%s/%s%s.html'
    return base_url % (CURRENT_PARLIAMENT_VERSION, law_year, fixed_width_law_num)


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

        elif matcher.check(prev_numart_nr, '(\d+)-(\d+)'):
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
        expected_numart_nrs.append('—')
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

    if matcher.check(line, '<tag goo="(\d+)" splah="(\d+)">'):
        goo, splah = matcher.result()
    '''

    match = None
    def check(self, line, test_string):
        self.match = re.match(test_string, line)
        return self.match != None

    def result(self):
        return self.match.groups()
