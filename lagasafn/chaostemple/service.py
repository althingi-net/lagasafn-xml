# FIXME: This is temporarily only returning untyped JSON as dicts and lists.
# Should be replaced with something that can generate a Pydantic schema from a
# Swagger API.
import requests
from requests import Response
from lagasafn.settings import CHAOSTEMPLE_API_URL

# FIXME: Hard-coded, but should be determined from codex index data, either
# `parliament_num` or timing.
parliament_num = 157


def _get(url: str):
    response: Response = requests.get(url)
    response.raise_for_status()
    return response.json()


def law_documents() -> list[dict]:
    url = "%s/law_documents?parliament_num=%d" % (CHAOSTEMPLE_API_URL, parliament_num)
    return _get(url)


def law_document(law_identifier: str) -> dict:
    url = "%s/law_document?law_identifier=%s" % (CHAOSTEMPLE_API_URL, law_identifier)
    return _get(url)
