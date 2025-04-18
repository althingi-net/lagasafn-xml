from lagasafn.exceptions import IntentParsingException
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
    art: _Element | None
    subart: _Element | None
    numarts: list[_Element]
    table: _Element | None

    def __init__(self):
        self.art = None
        self.subart = None
        self.numarts = []
        self.table = None


class IntentTracker:
    # Holds the information on the law that the intent impacts, inherited from
    # the `AdvertTracker`.
    affected_law_nr: str
    affected_law_year: int

    # Holds the original content to be parsed.
    original: _Element

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
        self.affected_law_nr = original.getparent().attrib["affected-law-nr"]
        self.affected_law_year = int(original.getparent().attrib["affected-law-year"])

        self.lines = super_iter(original.getchildren())
        self.intents = E("intents")

        # We load the first line and get ready to rumble.
        next(self.lines)

        # Configure cache for "current" text.
        self.cached_current_index = -1

    def affected_law_identifier(self) -> str:
        return "%s/%d" % (self.affected_law_nr, self.affected_law_year)

    def affected_law(self) -> Law:
        codex_version = self.original.getroottree().getroot().attrib["applied-to-codex-version"]
        return Law(self.affected_law_identifier(), codex_version)

    def get_codex_version(self):
        return self.original.getroottree().getroot().attrib["applied-to-codex-version"]

    def get_existing(self, xpath: str) -> _Element:
        # FIXME: Scheduled for deprecation in favor of `make_intent`.
        law = Law(self.affected_law_identifier(), self.get_codex_version())
        nodes = law.xml().xpath(xpath)
        if len(nodes) != 1:
            raise Exception("This method only supports results with a singular node. Update code to use `make_intent`.")
        return nodes[0]

    def get_existing_from_address(self, address: str) -> tuple[_Element, str]:
        # FIXME: Scheduled for deprecation in favor of `make_intent`.
        xpath = make_xpath_from_inner_reference(address)
        existing = self.get_existing(xpath)
        return (existing, xpath)

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

        xpath = make_xpath_from_inner_reference(address)

        existing = law.xml().xpath(xpath)
        if len(existing) == 0:
            raise IntentParsingException("Could not find XML content by address: %s" % address)

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
            },
            E("address", {"xpath": xpath }, address),
            E("existing", *existing),
        )

        return intent
