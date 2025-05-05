from django.http import HttpRequest
from lagasafn.constants import XML_FILENAME
from lagasafn.exceptions import BillException
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.utils import write_xml
from lxml import etree
from ninja import NinjaAPI

api = NinjaAPI(urls_namespace="bill")

@api.post("validate")
def bill_validate(request: HttpRequest):

    if "bill" not in request.POST.keys():
        raise BillException("Bill must be provided.")

    bill_xml_string = request.POST.get("bill")

    try:
        bill_xml = etree.fromstring(bill_xml_string)
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
        "something": "something",
    }
