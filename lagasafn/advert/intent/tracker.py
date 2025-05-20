from datetime import datetime
from lagasafn.models.law import Law
from lagasafn.pathing import make_xpath_from_inner_reference
from lagasafn.pathing import make_xpath_from_node
from lagasafn.utils import get_all_text
from lagasafn.utils import super_iter
from lxml.builder import E
from lxml.etree import _Element


class TargetGroup():
    # The `<inner>` tag that will contain the `<art>` or `<chapter>` or
    # whatever's being added to the actual law.
    inner: _Element | None

    def __init__(self):
        self.inner = None


class InnerTargetGroup():
    chapter: _Element | None
    art: _Element | None
    subart: _Element | None
    numarts: list[_Element]
    table: _Element | None

    def __init__(self):
        self.chapter = None
        self.art = None
        self.subart = None
        self.numarts = []
        self.table = None


class IntentTracker:
    # Holds the information on the law that the intent impacts, inherited from
    # the `AdvertTracker`.
    affected_law_nr: str | None
    affected_law_year: int | None

    # Holds the original content to be parsed.
    original: _Element

    # Holds the identifier of the advert.
    advert_identifier: str

    # Temporarily keeps `lines` while they are supplanted with sub-nodes to
    # deal with. See functions `set_lines` and `unset_lines`.
    lines_trace: list[super_iter]

    # Rather nodes than lines. Holds each child node of `original`, for better
    # control during parsing.
    lines: super_iter

    # Holds the intents as rendered after parsing.
    intents: _Element

    # Keeps track of inner targets, i.e. those that will end up being part of
    # actual legislation. Articles may be added to chapters, for instance.
    inner_targets: InnerTargetGroup

    # Keeps track of targets related to the intent.
    # Note the separate `inner_targets`.
    targets: TargetGroup

    # The current string is checked so often that we store it here instead of
    # running `get_all_text` on the XML over and over again.
    cached_current_index: int
    cached_current_text: str
    @property
    def current_text(self) -> str:
        if self.cached_current_index != self.lines.index:
            self.cached_current_index = self.lines.index
            self.cached_current_text = get_all_text(self.lines.current)
        return self.cached_current_text

    def __init__(self, original: _Element):
        self.inner_targets = InnerTargetGroup()
        self.targets = TargetGroup()

        self.original = original

        if (
            "affected-law-nr" in original.attrib
            and "affected-law-year" in original.attrib
        ):
            self.affected_law_nr = original.attrib["affected-law-nr"]
            self.affected_law_year = int(original.attrib["affected-law-year"])
        else:
            self.affected_law_nr = None
            self.affected_law_year = None

        self.advert_identifier = "%s/%s" % (
            self.original.getroottree().getroot().attrib["nr"],
            self.original.getroottree().getroot().attrib["year"],
        )

        self.lines_trace = []
        self.lines = super_iter(original.getchildren())

        self.intents = E("intents")

        # We load the first line and get ready to rumble.
        next(self.lines)

        # Configure cache for "current" text.
        self.cached_current_index = -1

    def set_lines(self, new_lines: list[_Element]):
        """
        Tugs the current lines away for temporarily working on a new set.
        Typically used when iteration of subnodes is required.
        """
        self.lines_trace.append(self.lines)
        self.lines = super_iter(new_lines)
        self.cached_current_index = -1

    def unset_lines(self):
        """
        Restores the previous set of lines, which were previously tugged away
        by `set_lines`.
        """
        self.lines = self.lines_trace.pop()
        self.cached_current_index = -1

    def set_affected_law_identifier(self, identifier: str):
        nr, year = identifier.split("/")
        self.affected_law_nr = nr
        self.affected_law_year = int(year)

    def affected_law_identifier(self) -> str | None:
        if self.affected_law_nr is None or self.affected_law_year is None:
            return None

        return "%s/%d" % (self.affected_law_nr, self.affected_law_year)

    def affected_law(self) -> Law:
        codex_version = self.original.getroottree().getroot().attrib["applied-to-codex-version"]
        return Law(self.affected_law_identifier(), codex_version)

    def get_codex_version(self):
        return self.original.getroottree().getroot().attrib["applied-to-codex-version"]

    def make_citizenship(self, name, born_year, born_country) -> _Element:
        """
        Creates a special intent for giving someone citizenship.
        """
        citizenship = E(
            "intent",
            {
                "action": "grant_citizenship",
                "name": name,
                "born-year": born_year,
                "born-country": born_country,
            },
        )
        return citizenship

    def make_repeal(self, repealed_law_identifier) -> _Element:
        """
        Creates a special kind of intent which communicates the repeal of law.
        """
        repeal = E(
            "intent",
            {
                "action": "repeal",
                "action-identifier": repealed_law_identifier,
            },
        )

        return repeal

    def make_enactment(
        self,
        timing: datetime,
        timing_type: str,
        extra: str = "",
        implemented_timing: datetime | None = None,
        implemented_timing_custom: str = "",
        address: str = "",
    ) -> _Element:
        """
        Creates a special kind of intent which communicates the enacting of the
        law, exceptions and particularities about it.

        Placed in a different function than `make_intent` altogether because
        the needs are radically different, and are likely to become even more
        different in the future.
        """

        xpath = ""
        if address != "":
            xpath = make_xpath_from_inner_reference(address)

        # NOTE: An `enactment` is strictly speaking an `intent`.
        enactment = E(
            "intent",
            {
                "action": "enact",
                "action-xpath": xpath,
                "timing": timing.strftime("%Y-%m-%d"),
                "timing-type": timing_type,
            },
        )

        if len(extra) > 0:
            enactment.attrib["extra"] = extra

        if implemented_timing is not None:
            enactment.attrib["implemented-timing"] = implemented_timing.strftime("%Y-%m-%d")

        if len(implemented_timing_custom) > 0:
            enactment.attrib["implemented-timing-custom"] = implemented_timing_custom

        return enactment


    def make_intent(self, action: str, address: str, node_hint: str = "") -> _Element:
        law = Law(self.affected_law_identifier(), self.get_codex_version())

        # Check if there is a common address of which this address is actually
        # a sub-address. This occurs when dealing with multiple intents in the
        # same article, for example.
        if "common-address" in self.intents.attrib:
            if address == "":
                # This may occur when a change is requested according to the
                # `common-address`, among changes made to sub-items of it.
                # Example:
                # - a-liður 58. gr. laga nr. 53/2024 (155)
                #   https://www.stjornartidindi.is/Advert.aspx?RecordID=53d9202f-a49b-434c-9ea3-52b65e22135f
                address = self.intents.attrib["common-address"]
            else:
                address = "%s %s" % (address, self.intents.attrib["common-address"])

            # There may be an `intents` parent to the `intents`, when we're
            # more than one level down in changes.
            #
            # Example:
            #  - A-stafl. 7. gr. laga nr. 68/2024:
            #    https://www.stjornartidindi.is/Advert.aspx?RecordID=559fef86-a7a2-4285-afd3-8f94a271e55f
            parent = self.intents.getparent()
            while (
                parent is not None
                and parent.tag == "intents"
            ):
                address = "%s %s" % (address, parent.attrib["common-address"])
                parent = parent.getparent()

        xpath = make_xpath_from_inner_reference(address)

        existing = law.xml().xpath(xpath)

        # FIXME: This should be refactored into a separate function such as
        # `tracker.add_intent` or similar, that figures this out based on what
        # has been added to `inner`. Until then, we rely on an optional
        # argument called `node_hint`. to determine the `action_node` when it's
        # determined by `inner` content.
        #
        # This may require further refactoring of `tracker.make_intent` so that
        # it returns some kind of `Intent` objects instead of an XML element.
        #
        # This may also free us from having to use `existing = ...` everywhere
        # in the parsing functions.
        action_xpaths = []
        for node in existing:
            action_node = node

            if node.tag == "art":
                if node_hint == "sen":
                    action_node = node.xpath("subart/paragraph")[-1]
                elif node_hint == "name":
                    action_node = node.xpath("name")[0]

            elif node.tag in ["numart", "subart"]:
                if node_hint in ["sen", "numart"]:
                    action_node = node.xpath("paragraph")[-1]

            action_xpaths.append(make_xpath_from_node(action_node))
        action_xpath = " | ".join(action_xpaths)

        intent = E(
            "intent",
            {
                "action": action,
                "action-xpath": action_xpath,
                "action-law-nr": self.affected_law_nr,
                "action-law-year": str(self.affected_law_year),
            },
            E("address", {"xpath": xpath }, address),
            E("existing", *existing),
        )

        return intent
