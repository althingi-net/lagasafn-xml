from django.http import HttpRequest
from lagasafn.constants import XML_FILENAME
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

    existing_filename = XML_FILENAME % (CURRENT_PARLIAMENT_VERSION, year, nr)

    write_xml(law, existing_filename)

    #import ipdb; ipdb.set_trace()

    # I was here. Going to see what I can do with these bills now.
    # I should commit and push this basic service when it's capable of receiving the files at all.
    return {
        "validated": True,
        "bill": {
            "nr": nr,
            "year": year,
        }
    }
