import re

def strip_links(text):
    '''
    Strips links from text. Also strips trailing whitespace after the link,
    because there is always a newline and a tab after the links in our input.
    '''

    regex = r'<a.*?>\s*(.*?)\s*</a>\s*'
    text = re.sub(regex, r'\1', text)

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

    '''
    def prev(self):
        self.index -= 1
        if self.index < 0:
            raise StopIteration
        return self.collection[self.index]
    '''

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
