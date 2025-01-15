from lagasafn.utils import super_iter
from lxml.etree import _Element
from lxml.etree import Element
from typing import cast


class TargetGroup:
    """
    This keeps track of what's being worked on when parsing sub-elements. For
    example, an `art` may belong either in the base XML document or in a
    `chapter` element, which is determined using this.
    """
    chapter: _Element | None = None


class AdvertTracker:
    """
    Keeps track of parsing of adverts.
    """

    # Container for information about what's being affected at any given point
    # in time. For example, when we run into "2. mgr.", this might contain
    # information about in which article, and subsequently in which law, based
    # on previously parsed content.
    #
    # This information doesn't always pop in the same places during the
    # parsing. For example, which law is being changed can show up in the name
    # of the advert, or in the name of a chapter.
    #
    # We will record as much about this as we can into each element in the
    # resulting advert XML.
    affected = {}

    # Contains the resulting XML that will be written to disk.
    xml: _Element

    # Contains a `super_iter`-ated set of nodes from the original advert.
    nodes: super_iter = super_iter([])

    # See `TargetGroup` class.
    targets: TargetGroup = TargetGroup()

    def __init__(self, xml_doc: _Element):
        self.xml = xml_doc

    def current_node(self) -> _Element:
        """
        Pass-through function to offer type hint and abstract the currently
        misleading nomenclature of `super_iter`.
        """
        return cast(_Element, self.nodes.current_line)
