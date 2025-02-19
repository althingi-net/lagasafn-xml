from django.http import HttpRequest
from django.shortcuts import render
from lagasafn.models.advert import AdvertManager
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION


def advert_list(request: HttpRequest):

    advert_index = AdvertManager.index(CURRENT_PARLIAMENT_VERSION)

    ctx = {
        "advert_index": advert_index,
    }
    return render(request, "advert/list.html", ctx)
