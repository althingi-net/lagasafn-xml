from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.settings import DATA_DIR
from os.path import join

PATCHES_BASE_DIR = join(DATA_DIR, "patches")

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
XML_FILENAME = join(DATA_DIR, "xml", CURRENT_PARLIAMENT_VERSION, "%d.%s.xml")  # % (law_year, law_num)
XML_INDEX_FILENAME = join(DATA_DIR, "xml", CURRENT_PARLIAMENT_VERSION, "index.xml")
XML_REFERENCES_FILENAME = join(DATA_DIR, "xml", CURRENT_PARLIAMENT_VERSION, "references.xml")

ERRORMAP_FILENAME = join("data", "json-maps", CURRENT_PARLIAMENT_VERSION, "errormap.json")
STRAYTEXTMAP_FILENAME = join("data", "json-maps", CURRENT_PARLIAMENT_VERSION, "straytextmap.json")
SPLITMAP_FILENAME = join("data", "json-maps", CURRENT_PARLIAMENT_VERSION, "splitmap.json")
PROBLEMS_FILENAME = join(DATA_DIR, "xml", CURRENT_PARLIAMENT_VERSION, "problems.xml")
