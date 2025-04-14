import re
from lagasafn.constants import ADVERT_FIXED_FILENAME
from lagasafn.constants import ADVERT_REMOTE_FILENAME
from lagasafn.constants import ADVERT_REMOTES_DIR
from lxml import etree
from lxml.etree import _Element
from os import listdir
from os.path import isfile


def get_original_advert_identifiers() -> list[str]:
    filenames = [
        f
        for f in listdir(ADVERT_REMOTES_DIR)
        if re.match(r"^\d{4}\.\d{1,3}\.remote\.xml$", f)
    ]

    identifiers = []
    for filename in filenames:
        parts = filename.split(".")
        identifiers.append("%s/%s" % (parts[1], parts[0]))

    return identifiers


def get_original_advert_xml(year: int, nr: int) -> _Element:

    filename = ADVERT_REMOTE_FILENAME % (year, nr)

    fixed_filename = ADVERT_FIXED_FILENAME % (year, nr)
    if isfile(fixed_filename):
        filename = fixed_filename

    xml_remote = etree.parse(filename).getroot()

    return xml_remote
