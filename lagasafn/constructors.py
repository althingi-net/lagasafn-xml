from copy import deepcopy
from lagasafn.contenthandlers import add_sentences
from lagasafn.contenthandlers import separate_sentences
from lagasafn.exceptions import LawException
from lxml.builder import E
from lxml.etree import _Element


def construct_node(base_node: _Element, text_to: str, name: str = "", nr_change: int = 1) -> _Element:
    """
    Constructs a Lagasafn-XML node from an already existing node.
    """

    # We copy the base node and remove all its children, so that we retain all
    # the attribute information, whatever it may be.
    node = deepcopy(base_node)
    for child in list(node):
        node.remove(child)

    # We then increase its `nr` by default, but respecting the `nr_change`
    # parameter for exceptions.
    if "nr-type" not in node.attrib or node.attrib["nr-type"] == "numeric":
        node.attrib["nr"] = str(int(node.attrib["nr"]) + nr_change)
    elif node.attrib["nr-type"] == "alphabet":
        node.attrib["nr"] = chr(ord(node.attrib["nr"]) + nr_change)
    else:
        raise LawException("Can't figure out 'nr-type' of node with tag: %s" % base_node.tag)

    # Add the actual content.
    node.append(E("nr-title", "%s." % node.attrib["nr"]))
    if len(name) > 0:
        node.append(E("name", name))
    sens = separate_sentences(text_to)
    add_sentences(node, sens)

    return node
