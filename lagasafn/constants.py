from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.settings import DATA_DIR
from os.path import join

# TODO: Make constants file less of a jungle.

JSON_MAP_BASE_DIR = join(DATA_DIR, "json-maps")
PATCHES_BASE_DIR = join(DATA_DIR, "patches")
XML_BASE_DIR = join(DATA_DIR, "xml")

LAW_FILENAME = join(
    DATA_DIR, "original", CURRENT_PARLIAMENT_VERSION, "%d%s.html"
)  # % (law_year, law_num)

CLEAN_FILENAME = join(
    DATA_DIR, "cleaned", "%d-%d.html"
)  # % (law_year, law_num)

PATCHED_FILENAME = join(
    DATA_DIR, "patched", "%d-%d.html"
)  # % (law_year, law_num)

PATCH_FILENAME = join(
    PATCHES_BASE_DIR, CURRENT_PARLIAMENT_VERSION, "%d-%d.html.patch"
)  # % (law_year, law_num)

ADVERT_REMOTES_DIR = join(
    DATA_DIR, "adverts", "remote"
)

ADVERT_DIR = join(
    DATA_DIR, "adverts", "xml"
)

XML_FILENAME = join(XML_BASE_DIR, CURRENT_PARLIAMENT_VERSION, "%d.%s.xml")  # % (law_year, law_num)
XML_INDEX_FILENAME = join(XML_BASE_DIR, CURRENT_PARLIAMENT_VERSION, "index.xml")
XML_REFERENCES_FILENAME = join(XML_BASE_DIR, CURRENT_PARLIAMENT_VERSION, "references.xml")

ERRORMAP_FILENAME = join(JSON_MAP_BASE_DIR, CURRENT_PARLIAMENT_VERSION, "errormap.json")
STRAYTEXTMAP_FILENAME = join(JSON_MAP_BASE_DIR, CURRENT_PARLIAMENT_VERSION, "straytextmap.json")
SPLITMAP_FILENAME = join(JSON_MAP_BASE_DIR, CURRENT_PARLIAMENT_VERSION, "splitmap.json")
PROBLEMS_FILENAME = join(XML_BASE_DIR, CURRENT_PARLIAMENT_VERSION, "problems.xml")
