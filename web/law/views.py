from django.conf import settings
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import render
from lagasafn.utils import traditionalize_law_nr
from law.models import Law
from law.models import LawManager
from os.path import join


def law_list(request):
    stats, laws = LawManager.index()

    ctx = {
        "stats": stats,
        "laws": laws,
    }
    return render(request, "law/list.html", ctx)


def law_show(request, identifier, view_type: str = "normal"):
    law = Law(identifier)

    ctx = {
        "law": law,
        "view_type": view_type,
    }

    return render(request, "law/show.html", ctx)


def law_show_cleaned(request, identifier):
    try:
        law_nr, law_year = identifier.split("/")
    except ValueError:
        raise Http404

    if identifier[0] == "m":
        # Pre-1885 law number.
        law_nr = traditionalize_law_nr(law_nr).strip("0")

    cleaned_filename = "%s-%s.html" % (law_year, law_nr)
    fullpath = join(settings.DATA_DIR, "..", "cleaned", cleaned_filename)
    with open(fullpath, "r") as f:
        content = f.read()

    return HttpResponse(content, content_type="text/html")
