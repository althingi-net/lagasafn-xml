from django.http import HttpRequest
from lagasafn.models.advert import Advert
from lagasafn.models.advert import AdvertIndex
from lagasafn.models.advert import AdvertIntentDetails
from lagasafn.models.advert import AdvertManager
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from ninja import Router


router = Router(tags=["Advert"])


@router.get(
    "/list",
    summary="Returns a list of all adverts.",
    operation_id="listAdverts",
    response=AdvertIndex,
)
def api_list(request: HttpRequest, codex_version: str = None):
    if codex_version is None:
        codex_version = CURRENT_PARLIAMENT_VERSION
    index = AdvertManager.index(codex_version)
    return index


@router.get(
    "/get",
    summary="Returns a single requested advert.",
    operation_id="getAdvert",
    response=Advert,
)
def api_get(request: HttpRequest, identifier: str):
    advert = Advert(identifier)
    return advert


@router.get(
    "/intents",
    summary="Returns intent details with comparisons.",
    operation_id="getAdvertIntents",
    response=AdvertIntentDetails,
)
def api_get_intents(request: HttpRequest, identifier: str):
    advert = Advert(identifier)
    return advert.get_intent_details()
