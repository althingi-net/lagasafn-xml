import re

def strip_markers(text):
    '''
    Strips markers from text.
    '''

    text = text.replace('…', '')
    text = text.replace('[', '')
    text = text.replace(']', '')
    text = re.sub(r'<sup style="font-size:60%"> \d+\) </sup>', '', text)

    while text.find('  ') > -1:
        text = text.replace('  ', ' ')

    # Only strip if there is content remaining, because we don't want to leave
    # empty entities.
    if text.strip() != '':
        text = text.strip()

    return text


def xml_lists_identical(one, two):
    '''
    Takes two lists of XML nodes and checks whether they have the same
    tagnames, texts (values) and attributes. Does not check subnodes.
    '''

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
