from copy import deepcopy
from lagasafn.contenthandlers import add_sentences
from lagasafn.contenthandlers import separate_sentences
from lagasafn.exceptions import LawException
from lagasafn.utils import is_roman
from lxml.builder import E
from lxml.etree import _Element
from roman import fromRoman
from roman import toRoman


def construct_node(base_node: _Element, text_to: str = "", name: str = "", nr_change: int = 1) -> _Element:
    """
    Constructs a Lagasafn-XML node from an already existing node.
    """

    # We copy the base node and remove all its children, so that we retain all
    # the attribute information, whatever it may be.
    node = deepcopy(base_node)
    for child in list(node):
        node.remove(child)

    # FIXME: Number-types are variously described in the XML as `nr-type` or
    # `number-type`. It should always be `nr-type`. To mitigate this problem,
    # we assign whichever is present to the variable `nr_type`.
    nr_type = ""
    if "nr-type" in node.attrib:
        nr_type = node.attrib["nr-type"]
    elif "number-type" in node.attrib:
        nr_type = node.attrib["number-type"]

    # We then increase its `nr` by default, but respecting the `nr_change`
    # parameter for exceptions.
    if nr_type in ["", "numeric"]:
        node.attrib["nr"] = str(int(node.attrib["nr"]) + nr_change)
    elif nr_type == "alphabet":
        node.attrib["nr"] = chr(ord(node.attrib["nr"]) + nr_change)
    elif nr_type == "roman":
        # FIXME: Chapter tags erroneously have their Arabic equivalent in the
        # `nr` attribute and the original Roman number in the `roman-nr`
        # attribute. This is the exact opposite to how Roman numerals are
        # treated elsewhere, for example in temporary clauses. The general rule
        # should be that the `nr` attribute contains the value in the format
        # that it's the most likely to be looked up by, which in the case of
        # chapters is Roman.
        #
        # Since fixing this is probably going to be a bit of a headache, we
        # mitigate the problem here until then, by detecting which way it's
        # being done and reacting accordingly. This special treatment should be
        # removed once the data is made consistent.
        if is_roman(node.attrib["nr"]):
            node.attrib["nr"] = toRoman(fromRoman(node.attrib["nr"]) + nr_change)
            node.attrib["roman-nr"] = str(int(node.attrib["roman-nr"]) + nr_change)
        else:
            node.attrib["nr"] = str(int(node.attrib["nr"]) + nr_change)
            node.attrib["roman-nr"] = toRoman(fromRoman(node.attrib["roman-nr"]) + nr_change)
    else:
        raise LawException("Can't figure out 'nr-type' of node with tag: %s" % base_node.tag)

    # Add nr-title, if appropriate.
    # NOTE: There are occasional examples of `subart`s with a `nr-title` but
    # the XML format currently (2025-04-28) does not account for them.
    if node.tag == "numart":
        node.append(E("nr-title", "%s." % node.attrib["nr"]))
    elif node.tag == "art":
        if nr_type == "roman":
            nr_title_text = "%s." % node.attrib["nr"]
        else:
            nr_title_text = "%s. gr." % node.attrib["nr"]
        node.append(E("nr-title", nr_title_text))
    elif node.tag == "chapter":
        node.append(E("nr-title", "%s. %s" % (node.attrib["roman-nr"], node.attrib["chapter-type"])))
    else:
        raise Exception("Don't know how to construct nr-title for tag: %s" % node.tag)

    # Add name, if present.
    if len(name) > 0:
        node.append(E("name", name))

    # Finally, add sentences.
    if len(text_to) > 0:
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


def construct_temp_chapter_from_art(base_node: _Element) -> _Element:
    """
    When a law only has one temporary clause, it is an article. When there are
    more than one, the term "temporary clauses" begins to refer to a chapter,
    with articles numbered in Roman numerals within it.

    So when there is an existing, single, temporary article, but more temporary
    articles get added, what really happens is that the temporary article turns
    into a chapter, the existing one gets placed in it and numbered as 1 (or
    "I" in Roman numerals) and the new ones added to that chapter.

    This function takes an existing temporary article, and returns a chapter
    that contains the article already present.

    Example:
    - 4. gr. laga nr. 73/2024
      https://stjornartidindi.is/Advert.aspx?RecordID=417b28c4-f82c-46c3-a9a8-09ec25807c30
    """
    if base_node.tag != "art":
        raise LawException(
            "Function 'construct_temp_chapter_from_art' expects a tag 'art' but received: %s" % base_node.tag
        )

    # Basic skeleton of our new article.
    art = E(
        "art",
        {
            "nr": "I",
            "roman-nr": "1",
            "number-type": "roman",
        },
    )

    # Copy the contents from the existing one.
    for elem in deepcopy(list(base_node)):
        art.append(elem)

    # Engulf the whole thing in a chapter.
    chapter = E(
        "chapter",
        {
            "nr-type": "temporary-clauses",
            "nr": "t",
        },
        art
    )

    return chapter
