from django.conf import settings
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import render
from lagasafn.utils import traditionalize_law_nr
from law.models import Law
from law.models import LawManager
from os.path import isfile
from os.path import join


def law_search(request):
    ctx = {}
    return render(request, "law/search.html", ctx)


def law_list(request):
    stats, laws = LawManager.index()

    ctx = {
        "stats": stats,
        "laws": laws,
    }
    return render(request, "law/list.html", ctx)


def law_show(request, identifier, view_type: str = "normal"):
    law = Law(identifier)

    references = law.get_references()

    interim_laws = law.get_interim_laws()
    ongoing_issues = law.get_ongoing_issues()

    ctx = {
        "law": law,
        "references": references,
        "interim_laws": interim_laws,
        "ongoing_issues": ongoing_issues,
        "view_type": view_type,
    }
    return render(request, "law/show.html", ctx)


def law_show_patched(request, identifier):
    """
    Shows the cleaned and patched law for comparing in tests. If a patched
    version does not exist, it reverts to the cleaned version.
    """

    try:
        law_nr, law_year = identifier.split("/")
    except ValueError:
        raise Http404

    if identifier[0] == "m":
        # Pre-1885 law number.
        law_nr = traditionalize_law_nr(law_nr).strip("0")

        # In the single case of law nr. m00d00/1275, we will have an empty
        # string here.
        if len(law_nr) == 0:
            law_nr = "0"

    filename = "%s-%s.html" % (law_year, law_nr)

    # First check if a patched version exists...
    fullpath = join(settings.DATA_DIR, "..", "patched", filename)
    if not isfile(fullpath):
        # ...and if not, go for a cleaned one.
        fullpath = join(settings.DATA_DIR, "..", "cleaned", filename)

    with open(fullpath, "r") as f:
        content = f.read()

    return HttpResponse(content, content_type="text/html")


def content_search(request):
    search_text = request.GET.get("search_text", "")

    results = None
    if len(search_text):
        results = LawManager.content_search(search_text)

    ctx = {
        "search_text": search_text,
        "results": results,
    }
    return render(request, "law/content_search.html", ctx)
