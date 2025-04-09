from lagasafn.models.law import Law
from lagasafn.pathing import make_xpath_from_inner_reference
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
        law = Law(self.affected_law_identifier(), self.get_codex_version())
        target = law.xml().xpath(xpath)[0]
        return target

    def get_existing_from_address(self, address: str) -> tuple[_Element, str]:
        xpath = make_xpath_from_inner_reference(address)
        existing = self.get_existing(xpath)
        return (existing, xpath)
