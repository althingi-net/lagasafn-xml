import re
from datetime import datetime

from django.http import HttpRequest
from django.http import HttpResponse
from lagasafn.constants import SEARCH_INDEX_FILENAME
from lagasafn.exceptions import NoSuchElementException
from lagasafn.exceptions import NoSuchLawException
from lagasafn.exceptions import ReferenceParsingException
from lagasafn.models.law import Law
from lagasafn.models.law import LawIndex
from lagasafn.models.law import LawManager
from lagasafn.pathing import get_segment
from lagasafn.references import parse_reference_string
from lagasafn.search import SearchEngine
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.utils import write_xml
from lxml import etree
from ninja import File
from ninja import Router
from ninja.errors import HttpError
from ninja.files import UploadedFile
from datetime import datetime


router = Router(tags=["Law"])

# Initialize the global search engine
searchengine = SearchEngine(SEARCH_INDEX_FILENAME)


@router.get(
    "search/",
    summary="Search legal codex by content.",
    operation_id="search",
)
def api_search(request, q: str):
    """
    Returns search-specific results explaining what was found given a provided
    content query.
    """
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


@router.get(
    "parse-reference/",
    summary="Parse human-readable legal reference.",
    operation_id="parseReferenceString",
)
def api_parse_reference_string(request, reference):
    """
    Parse a human-readable legal reference and return path and content
    information.
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


@router.get(
    "get-segment/",
    summary="Get segment from a law in the legal codex.",
    operation_id="getSegment",
)
def api_get_segment(request, law_nr: str, law_year: int, xpath: str):
    """
    Takes identity information (nr/year) and an XPath string, and returns the
    XML content found in the corresponding legal codex."
    """
    try:
        law_year = int(law_year)
        return get_segment(law_nr, law_year, xpath)
    except NoSuchLawException:
        raise HttpError(400, "No such law found.")
    except NoSuchElementException:
        raise HttpError(404, "Could not find requested element.")


@router.post(
    "normalize/",
    summary="Normalize a law XML document.",
    operation_id="normalize",
)
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
    # minister_clause = xml_doc.find("minister-clause")
    # encoded_clause = ""
    # for child in minister_clause:
    #    encoded_clause += etree.tostring(child, encoding="unicode")
    # encoded_clause = encoded_clause.replace(">", "> ")
    # encoded_clause = encoded_clause.replace("<", " <")
    # encoded_clause = encoded_clause.replace("  ", " ").strip()
    # for child in list(minister_clause):
    #    minister_clause.remove(child)
    # minister_clause.text = encoded_clause

    xml_string = write_xml(xml_doc)

    return HttpResponse(xml_string, content_type="text/xml")


@router.get(
    "/list",
    summary="Returns a list of all laws.",
    operation_id="listLaws",
    response=LawIndex,
)
def api_list(request: HttpRequest, codex_version: str = None):
    """
    Returns a list of all laws in the specified codex version.

    If codex_version is provided, it must be a valid codex version identifier.
    """
    # Default behavior: current codex version.
    if codex_version is None:
        codex_version = CURRENT_PARLIAMENT_VERSION
    else:
        # Validate that the version exists
        versions = LawManager.codex_versions()
        if codex_version not in versions:
            raise HttpError(
                400,
                f"Invalid codex version '{codex_version}'. Available versions: {', '.join(versions)}",
            )

    index = LawManager.index(codex_version)
    return index


@router.get(
    "/codex-versions",
    summary="Returns a list of available codex versions.",
    operation_id="listCodexVersions",
    response=list[str],
)
def api_codex_versions(request: HttpRequest):
    """
    Returns a list of available codex versions
    """
    return LawManager.codex_versions()


@router.get(
    "/get",
    summary="Returns a single requested law.",
    operation_id="getLaw",
    response=Law,
)
def api_get(request: HttpRequest, identifier: str, version: str = None):
    """
    Returns a single requested law.

    - A version identifier (e.g. "154b", "155", "156a") – loads from that codex version.
    - A version identifier followed by a date (e.g. "154b-2024-07-12") – loads from the
        applied XML for the advert that affects this law in that codex version with the specified
        enact timing date (YYYY-MM-DD format).
    - If version is not provided, defaults to the current parliament version.
    """

    # Default behavior: current codex version.
    if version is None:
        return Law(identifier, CURRENT_PARLIAMENT_VERSION)

    match = re.match(
        r"^(?P<codex>\d{3}[a-z]?)(?:-(?P<date>\d{4}-\d{2}-\d{2}))?$", version
    )
    if not match:
        raise HttpError(400, f"Invalid version format: {version}")

    codex_version = match.group("codex")
    date = match.group("date")

    print(codex_version)
    # Load the law. If a date is provided, it's an applied version from an advert.
    # Otherwise, it's the base codex version.
    try:
        return Law(identifier, codex_version, applied_timing=date)
    except (NoSuchLawException, OSError):
        if date:
            error_msg = f"Applied version for law '{identifier}' and version '{codex_version}-{date}' doesn't exist."
        else:
            error_msg = (
                f"No such law '{identifier}' in codex version '{codex_version}'."
            )
        raise HttpError(404, error_msg)
