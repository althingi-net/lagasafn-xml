from django.http import HttpRequest
from lagasafn.constants import BILL_FILENAME
from lagasafn.exceptions import BillException
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.utils import write_xml
from lxml import etree
from ninja import NinjaAPI
from ninja.parser import Parser

api = NinjaAPI(urls_namespace="bill", parser=None)

@api.post("validate")
def bill_validate(request: HttpRequest):
    """
       Validate bill XML provided as POST body.

       Example: curl -H 'Content-Type: application/xml'  -X POST http://10.110.0.2:9000/api/bill/validate --data '<bill><title>test</title><law nr="5" year="1995">test</law></bill>'
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

@api.post("publish")
def bill_publish(request: HttpRequest):
    """
       Publish bill XML provided as POST body.

       Example: curl -H 'Content-Type: application/xml'  -X POST http://10.110.0.2:9000/api/bill/publish --data '<bill><title>test</title><law nr="5" year="1995">test</law></bill>'
    """

    bill_xml_string = request.body

    try:
        bill_xml = etree.fromstring(request.body)
    except Exception:
        raise BillException("Invalid XML provided.")

    law = bill_xml.find("law")
    nr = law.attrib["nr"]
    year = int(law.attrib["year"])

    # FIXME: Support custom bill publishing number.
    existing_filename = BILL_FILENAME % (CURRENT_PARLIAMENT_VERSION, 1, year, nr)

    write_xml(law, existing_filename)

    return {
        "published": True,
        "bill": {
            "nr": nr,
            "year": year,
        }
    }
