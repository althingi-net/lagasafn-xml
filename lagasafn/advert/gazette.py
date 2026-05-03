import json
import requests
from datetime import datetime
from lagasafn.constants import ADVERT_API_ADVERTS
from lagasafn.constants import ADVERT_GAZETTE_CACHE_FILENAME
from lagasafn.exceptions import AdvertException
from pathlib import Path


class GazetteInfo:
    """
    Gazette-specific information about an advert. Purposefully restricted to
    what we actually need. There is more data available in the ingredient data.
    """
    id: str
    publication_date: datetime
    signature_date: datetime


def get_gazette_info(law_identifier: str) -> GazetteInfo:
    nr, year = [int(p) for p in law_identifier.split("/")]
    cache_path = Path(ADVERT_GAZETTE_CACHE_FILENAME % (year, nr))

    if cache_path.is_file():
        with open(cache_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

    else:
        # Get remote data.
        url = ADVERT_API_ADVERTS % law_identifier
        response = requests.get(url)
        if response.status_code != 200:
            raise AdvertException("Failed retrieving gazette info for %s" % law_identifier)

        # Make sure this is JSON data.
        try:
            raw = response.json()
        except Exception:
            raise AdvertException("Expected particular JSON data from gazette API, got something else")

        # Write to cache file.
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2)

    advert = None
    for remote_advert in raw["adverts"]:
        if remote_advert["publicationNumber"]["full"] == law_identifier:
            advert = remote_advert

    if advert is None:
        raise AdvertException("Couldn't find requested advert %s in raw data" % law_identifier)

    info = GazetteInfo()
    info.id = advert["id"]
    info.publication_date = datetime.fromisoformat(advert["publicationDate"])
    info.signature_date = datetime.fromisoformat(advert["signatureDate"])

    return info
