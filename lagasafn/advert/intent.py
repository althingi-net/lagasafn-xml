import json
from lagasafn.advert.tracker import AdvertTracker
from lagasafn.exceptions import AdvertParsingException
from lagasafn.models.intent import IntentModel
from lagasafn.models.intent import IntentModelList
from lagasafn.utils import get_all_text
from lagasafn.utils import Matcher
from lagasafn.utils import super_iter
from lagasafn.utils import write_xml
from lxml import etree
from lxml.builder import E
from lxml.etree import _Element
from openai import OpenAI
from typing import List


def get_intents_by_ai(tracker: AdvertTracker, original: _Element):
    intents = []

    with open("data/prompts/intent-parsing.md") as r:
        prompt = r.read()

        # Fill in necessary information.
        # TODO: Replace this with proper Django templating.
        prompt = prompt.replace("{affected_law_nr}", tracker.affected["law-nr"])
        prompt = prompt.replace("{affected_law_year}", tracker.affected["law-year"])

    xml_text = write_xml(original)

    client = OpenAI()

    completion = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Meðfylgjandi XML skjal 'remote.xml' er hér: %s" % xml_text },
        ],
        response_format=IntentModelList,
    )

    items = json.loads(completion.choices[0].message.to_dict()["content"])["items"]

    intents = E("intents")
    for item in items:
        # Construct an XML element from the intent model.
        intent = E("intent")
        intents.append(intent)
        for key in item.keys():
            # Respecting XML conventions using dashes instead of underscores.
            element_name = key.replace("_", "-")
            value = item[key]

            intent.append(E(element_name, value))

    return intents


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
