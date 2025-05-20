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

    # Add nr-title, if appropriate.
    # NOTE: There are occasional examples of `subart`s with a `nr-title` but
    # the XML format currently (2025-04-28) does not account for them. This
    # condition should be removed if and when the XML format gets updated to
    # include them. Until then, they are effectively just normal sentences.
    if node.tag != "subart":
        node.append(E("nr-title", "%s." % node.attrib["nr"]))

    # Add name, if present.
    if len(name) > 0:
        node.append(E("name", name))

    # Finally, add sentences.
    sens = separate_sentences(text_to)
    add_sentences(node, sens)

    return node


def construct_sens(base_node: _Element, text_to, nr_change: int = 0) -> list[_Element]:
    if base_node.tag != "sen":
        raise LawException("Function 'construct_sens' requires 'base_node' to be a 'sen' node.")

    # Result value.
    sens = []

    nr_start = int(base_node.attrib["nr"])
    sentences = separate_sentences(text_to)
    for i, sentence in enumerate(sentences):
        sens.append(E("sen", {"nr": str(nr_start+i+nr_change) }, sentence))

    return sens
