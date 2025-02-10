from django.conf import settings
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import render
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.utils import traditionalize_law_nr
from lagasafn.models import Law
from lagasafn.models import LawManager
from os.path import isfile
from os.path import join

from lagasafn.rted import rted, EditType


def law_search(request):
    ctx = {"q": request.GET.get("q", "")}
    return render(request, "law/search.html", ctx)


def law_list(request):
    return render(request, "law/list.html")


def law_show(request, identifier, view_type: str = "normal"):
    law = Law(identifier, CURRENT_PARLIAMENT_VERSION)

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


def law_compare(request):
    codexa = request.GET.get("codexa", "154a")
    codexb = request.GET.get("codexb", "154b")
    lawref = request.GET.get("lawref", "7/2022")
    law1 = Law(lawref, codex=codexa)
    law2 = Law(lawref, codex=codexb)

    # We're going to walk through both laws, and compare them chunk by chunk.
    # If a chunk is missing in one of the laws, we'll leave a blank for that
    # law but include the chunk from the other law.
    #
    # It's possible that law1 will have a chunk that law2 doesn't have, and vice
    # versa. We mustn't miss anything!
    # 
    # The output is a list of chunks, each chunk being a dictionary containing
    # "a" from law1, "b" from law2, and "diff" which is a boolean indicating
    # whether the two chunks are different.
    chunks = []

    print("Law 1: ", law1.xml())
    print("Law 2: ", law2.xml())

    # We'll walk through the chunks of both laws.
    cost, script = rted(law1.xml().getroot(), law2.xml().getroot())
    script_source_map = {op.source: op for op in script}
    script_target_map = {op.target: op for op in script}

    a = law1.iter_structure()
    b = law2.iter_structure()

    def determine_chunk(c1, c2, script):
        if c1 in script_source_map.keys():
            if script_source_map[c1].edit_type == EditType.Delete:
                return {"a": c1, "b": None, "diff": True}
            if script_source_map[c1].edit_type == EditType.Change:
                return {"a": c1, "b": script_source_map[c1].target, "diff": True}

        if c2 in script_target_map.keys():
            if script_target_map[c2].edit_type == EditType.Insert:
                return {"a": None, "b": c2, "diff": True}

        # There's no difference between the two chunks.
        return {"a": c1, "b": c2, "diff": False}

    while True:
        c1 = next(a, None)
        c2 = next(b, None)
        if c1 is None and c2 is None:
            break
        chunks.append(determine_chunk(c1, c2, script))
    

    ctx = {
        "lawref": lawref,
        "codexa": codexa,
        "codexb": codexb,
        "chunks": chunks,
    }
    return render(request, "law/compare.html", ctx)


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
        results = LawManager.content_search(search_text, CURRENT_PARLIAMENT_VERSION)

    ctx = {
        "search_text": search_text,
        "results": results,
    }
    return render(request, "law/content_search.html", ctx)
