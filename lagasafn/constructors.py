from copy import deepcopy
from lagasafn.contenthandlers import add_sentences
from lagasafn.contenthandlers import separate_sentences
from lagasafn.exceptions import LawException
from lxml.builder import E
from lxml.etree import _Element


def construct_numart(text_to: str, name: str = "", base_numart: _Element | None = None, nr_change: int = 1) -> _Element:
    """
    Constructs a `numart` XML element from the information provided.
    """

    if base_numart is None:
        raise LawException("Unimplemented: Function 'construct_numart' currently requires 'base_numart'.")

    # We copy the base `numart` and remove all its children, so that we retain
    # all the attribute information, whatever it may be.
    numart = deepcopy(base_numart)
    for child in numart.getchildren():
        numart.remove(child)

    # We then increase its `nr` by default, but respecting the `nr_change`
    # parameter for exceptions.
    # NOTE: Only simple increases are supported for now. This is where you
    # should add support for Roman numerals if needed later.
    numart.attrib["nr"] = str(int(numart.attrib["nr"]) + nr_change)

    # Add the actual content.
    numart.append(E("nr-title", "%s." % numart.attrib["nr"]))
    if len(name) > 0:
        numart.append(E("name", name))
    sens = separate_sentences(text_to)
    add_sentences(numart, sens)

    return numart
