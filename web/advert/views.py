from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import render
from lagasafn.models.advert import Advert
from lagasafn.models.advert import AdvertManager
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION


def advert_list(request: HttpRequest) -> HttpResponse:

    advert_index = AdvertManager.index(CURRENT_PARLIAMENT_VERSION)

    ctx = {
        "advert_index": advert_index,
    }
    return render(request, "advert/list.html", ctx)


def advert_show(request: HttpRequest, identifier: str) -> HttpResponse:

    advert = Advert(identifier)

    ctx = {
        "advert": advert,
    }
    return render(request, "advert/show.html", ctx)
