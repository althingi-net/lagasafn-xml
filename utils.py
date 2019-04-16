import re
import roman
import subprocess

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
