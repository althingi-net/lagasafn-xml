from django.http import HttpResponse
from lagasafn.exceptions import NoSuchElementException
from lagasafn.exceptions import NoSuchLawException
from lagasafn.exceptions import ReferenceParsingException
from lagasafn.pathing import get_segment
from lagasafn.references import parse_reference_string
from lagasafn.utils import write_xml
from lxml import etree
from ninja import File
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.files import UploadedFile
from .searchengine import SearchEngine
from datetime import datetime

api = NinjaAPI(urls_namespace="law")

# Initialize the global search engine
searchengine = SearchEngine("search_index.pkl")

@api.get("search/")
def api_search(request, q: str):
    start_time = datetime.now()
    results = searchengine.search(q)
    end_time = datetime.now()
    return { 
        "query": q, 
        "time": (end_time - start_time).total_seconds(),
        "metadata": results.metadata,
        "refs": results.refs,
        "results": results.sort(),
    }


@api.get("parse-reference/")
def api_parse_reference_string(request, reference):
    """
    An API version of `parse_reference_string`.
    """
    try:
        xpath, law_nr, law_year = parse_reference_string(reference)

        segment = get_segment(law_nr, law_year, xpath)

        return {
            "xpath": xpath,
            "law_nr": law_nr,
            "law_year": law_year,
            "segment": segment,
        }

    except ReferenceParsingException as ex:
        raise HttpError(500, "Confused by: %s" % ex.args[0])


@api.get("get-segment/")
def api_get_segment(request, law_nr: str, law_year: int, xpath: str):
    """
    An API version of `get_segment`.
    """
    try:
        law_year = int(law_year)
        return get_segment(law_nr, law_year, xpath)
    except NoSuchLawException:
        raise HttpError(400, "No such law found.")
    except NoSuchElementException:
        raise HttpError(404, "Could not find requested element.")


@api.post("normalize/")
def api_normalize(request, input_file: UploadedFile = File(...)):
    """
    Takes an uploaded XML law and makes sure that it is formatted in the same
    way as the codex. Useful for comparison.
    """

    input_data = input_file.read()

    xml_doc = etree.fromstring(input_data)

    # Re-encode `minister-clause` because it's actually HTML with some
    # exporting quirks (from the original HTML-exporting software) that we
    # also imitate.
    # FIXME: Disabled for now because it's screwing things up rather than
    # fixing them. Remove comment or fix code depending on what kind of problem
    # this becomes later.
    #minister_clause = xml_doc.find("minister-clause")
    #encoded_clause = ""
    #for child in minister_clause:
    #    encoded_clause += etree.tostring(child, encoding="unicode")
    #encoded_clause = encoded_clause.replace(">", "> ")
    #encoded_clause = encoded_clause.replace("<", " <")
    #encoded_clause = encoded_clause.replace("  ", " ").strip()
    #for child in list(minister_clause):
    #    minister_clause.remove(child)
    #minister_clause.text = encoded_clause

    xml_string = write_xml(xml_doc)

    return HttpResponse(xml_string, content_type="text/xml")
