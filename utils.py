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
