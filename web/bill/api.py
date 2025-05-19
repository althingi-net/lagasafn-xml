from django.http import HttpRequest
from lagasafn.constants import BILLMETA_FILENAME, BILL_FILENAME
from lagasafn.exceptions import BillException
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION, BASE_DIR
from lagasafn.utils import write_xml
from lxml import etree
from ninja import NinjaAPI
from ninja.parser import Parser
from git import Repo
from time import sleep

api = NinjaAPI(urls_namespace="bill", parser=None)

@api.exception_handler(BillException)
def service_unavailable(request, exc):
    """
    Handle exceptions gracefully. Specify custom HTTP error code and return with message intended.
    """

    return api.create_response(
        request,
        { "message": exc.__str__() },
        status=400,
    )

@api.post("meta")
def bill_meta(request: HttpRequest):
    """
       Publish bill meta XML data as POST body.

       Example: curl -H 'Content-Type: application/xml'  -X POST http://127.0.0.1:9000/api/bill/meta --data '<bill><lagasafnID>1</lagasafnID><title>Skógræktarlög</title><description>Frumvarp um eflingu skógræktar á Íslandi</description></bill>'
    """

    bill_xml_string = request.body

    try:
        bill_xml = etree.fromstring(request.body)
    except Exception:
        raise BillException("Invalid XML provided.")

    title = bill_xml.find("title")
    description = bill_xml.find("description")
    bill_nr = int(bill_xml.find("lagasafnID").text)

    # Determine file name for bill meta, write XML to data directory.
    existing_filename = BILLMETA_FILENAME % (CURRENT_PARLIAMENT_VERSION, bill_nr)

    write_xml(bill_xml, existing_filename)

    return {
        "bill": {
            "saved": True,
            "title": title.text,
            "description": description.text,
        }
    }

@api.post("document/validate")
def bill_validate(request: HttpRequest):
    """
       Validate bill XML provided as POST body.

       Example: curl -H 'Content-Type: application/xml'  -X POST http://10.110.0.2:9000/api/bill/document/validate --data '<bill><title>test</title><law nr="5" year="1995">test</law></bill>'
    """

    bill_xml_string = request.body

    try:
        bill_xml = etree.fromstring(request.body)
    except Exception:
        raise BillException("Invalid XML provided.")

    law = bill_xml.find("law")
    nr = law.attrib["nr"]
    year = int(law.attrib["year"])

    return {
        "validated": True,
        "bill": {
            "nr": nr,
            "year": year,
        }
    }

@api.post("{bill_id}/document/publish")
def bill_publish(request: HttpRequest, bill_id):
    """
       Publish bill XML provided as POST body.

       Example: curl -H 'Content-Type: application/xml'  -X POST http://127.0.0.1:9000/api/bill/document/publish --data '<bill><title>test</title><law nr="5" year="1995">test</law></bill>'
    """

    bill_xml_string = request.body

    try:
        bill_xml = etree.fromstring(request.body)
    except Exception:
        raise BillException("Invalid XML provided.")

    # Attempt to determine law nr. and year.
    law = bill_xml.find("law")
    law_nr = law.attrib["nr"]
    law_year = int(law.attrib["year"])

    # Determine bill number
    bill_nr = int(bill_id)

    # Determine file name for bill, write XML to data directory.
    existing_filename = BILL_FILENAME % (CURRENT_PARLIAMENT_VERSION, bill_nr, law_year, law_nr)

    write_xml(law, existing_filename)

    # The endpoint may be called rapidly in succession, which
    # can cause one thread to have called git commit, causing a lock
    # to be placed, while another one is doing exactly the same. This
    # causes exceptions.
    #
    # Thus, we try a few times to commit the change, with increasingly
    # longer sleep time between attempts.

    failureCnt = 0

    while failureCnt < 10:
       try:
           repo = Repo.init(BASE_DIR)
           repo.index.add(existing_filename)
           repo.index.commit("Publish bill nr. " + str(bill_nr) + "/" + CURRENT_PARLIAMENT_VERSION + ", law " + str(law_nr) + "/" + str(law_year))
           break; # On success, break out of the loop.
       except Exception:
           failureCnt += 1
           sleep(failureCnt * 1)

    return {
        "published": True,
        "bill": {
            "nr": law_nr,
            "year": law_year,
        }
    }
