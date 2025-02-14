import json
from lagasafn.models.intent import IntentModel
from lagasafn.utils import get_all_text
from lagasafn.utils import Matcher
from lagasafn.utils import super_iter
from lxml import etree
from lxml.etree import _Element
from openai import OpenAI
from typing import List


def get_intent_by_ai(original: _Element):
    raise Exception("Unimplemented.")

    xml_text = etree.tostring(
        original,
        encoding="unicode",
        pretty_print=True
    ).replace(
        '\xa0', ' '
    ).replace(
        '&#160;', ' '
    ).strip()

    client = OpenAI()

    completion = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You will take in Icelandic text from a chunk of XML that describes in human language changes to existing laws."},
            {"role": "user", "content": "Here is the XML content: %s" % xml_text },
        ],
        response_format=IntentModel,
    )

    response = completion.choices[0].message
    json_goo = json.loads(response.to_dict()["content"])
    intent = IntentModel(**json_goo)

    return intent


def get_intents(original: _Element) -> List[_Element]:
    matcher = Matcher()
    intents: List[_Element] = []

    lines = super_iter(original.findall("p"))

    first_line = get_all_text(next(lines))

    if matcher.check(first_line, r"Við lögin bætast (.*) ákvæði til bráðabirgða, svohljóðandi:"):
        # Continue after having checked the first line.
        for line in lines:
            text = get_all_text(line)

            if matcher.check(text, r"([a-z])\. \(([A-Z])\.\)"):
                unused, temp_roman_num = matcher.result()
                # Incomplete. The plan is to try text analysis first but resort
                # to AI if needed, and then ask the user for confirmation on
                # the AI's conclusions.
                #
                # Make sure to also examine incomplete
                # `lagasafn.advert.conversion.tracker.IntentTracker` class.
                import ipdb; ipdb.set_trace()

    return intents
