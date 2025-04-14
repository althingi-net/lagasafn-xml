from lagasafn.models.law import Law
from lagasafn.pathing import make_xpath_from_inner_reference
from lagasafn.pathing import make_xpath_from_node
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
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

    def make_intent(self, action: str, address: str) -> _Element:
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

        if (
            len(existing) == 1
            # FIXME: This `action == "add"` condition here is bogus but
            # retained because we need it to keep compatibility with changes in
            # the short term (2025-04-11). Remove it, and adjust the XML so
            # that it targets the last paragraph of `numart`s and `subart`s
            # instead of targeting the entire `numart` or `subart`.
            and action in ["add", "add_text"]
            and existing[0].tag in ["numart", "subart"]
        ):
            # When adding to the specified tags, we always want to target the
            # last `paragraph` inside them.
            action_node = existing[0].xpath("paragraph")[-1]
            action_xpath = make_xpath_from_node(action_node)
        else:
            action_xpath = " | ".join(
                [make_xpath_from_node(n) for n in existing]
            )

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
