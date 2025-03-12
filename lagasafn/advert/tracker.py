import re
from lagasafn.exceptions import AdvertParsingException
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
    art: _Element | None = None
    temp_clause: _Element | None = None


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
    affected: dict = {}

    # Contains the resulting XML that will be written to disk.
    xml: _Element

    # Contains a `super_iter`-ated set of nodes from the original advert.
    nodes: super_iter = super_iter([])

    # See `TargetGroup` class.
    targets: TargetGroup = TargetGroup()

    def __init__(self, xml_doc: _Element):
        self.affected = {}
        self.xml = xml_doc

    def current_node(self) -> _Element:
        """
        Pass-through function to offer type hint and abstract the currently
        misleading nomenclature of `super_iter`.
        """
        return cast(_Element, self.nodes.current)

    def detect_affected_law(self, text: str, node: _Element) -> bool:

        # First hurdle. We must detect some string that dictates that this
        # refers to affected law.
        text = text.lower()
        if not (
            "um breytingu á lögum" in text
            or text.startswith("breyting á lögum")
        ):
            return False

        # Figure out which laws are being changed according to the given text.
        # This may be a chapter name, an article title or even the law's title.
        # If nothing is found, then probably multiple laws are being changed
        # and this information will be inside chapters.
        found = re.findall(r"nr\. (\d{1,3})\/(\d{4})", text)
        if len(found) != 1:
            if len(found) > 1:
                # This never happened between 2024-04-12 and 2025-01-13 at least, but
                # is placed here to prevent mistakes in the future.
                raise AdvertParsingException(
                    "Don't know how to handle more than one law number in advert title."
                )

            # At this point we've deduced that while there is an affected law,
            # their number are designated in following chapters or articles.
            return False

        nr, year = found[0]

        # Remember this for future reference.
        self.affected["law-nr"] = nr
        self.affected["law-year"] = year

        return True
