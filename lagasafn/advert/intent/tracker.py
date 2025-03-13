from lagasafn.utils import get_all_text
from lagasafn.utils import super_iter
from lxml.builder import E
from lxml.etree import _Element


class TargetGroup():
    # The `<inner>` tag that will contain the `<art>` or `<chapter>` or
    # whatever's being added to the actual law.
    inner: _Element | None = None


class InnerTargetGroup():
    art: _Element | None = None


class IntentTracker:
    # Holds the original content to be parsed.
    original: _Element

    # Rather nodes than lines. Holds each child node of `original`, for better
    # control during parsing.
    lines: super_iter

    # Holds the intents as rendered after parsing.
    intents: _Element

    # Keeps track of inner targets, i.e. those that will end up being part of
    # actual legislation. Articles may be added to chapters, for instance.
    inner_targets: InnerTargetGroup = InnerTargetGroup()

    # Keeps track of targets related to the intent.
    # Note the separate `inner_targets`.
    targets: TargetGroup = TargetGroup()

    # The current string is checked so often that we store it here instead of
    # running `get_all_text` on the XML over and over again.
    current_text: str

    def __init__(self, original: _Element):
        self.original = original
        self.lines = super_iter(original.getchildren())
        self.intents = E("intents")

        # We load the first line and get ready to rumble.
        next(self.lines)
        self.current_text = get_all_text(self.lines.current)
