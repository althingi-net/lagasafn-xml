import os
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.settings import DATA_DIR

LAW_FILENAME = os.path.join(
    DATA_DIR, "original", CURRENT_PARLIAMENT_VERSION, "%d%s.html"
)  # % (law_year, law_num)
CLEAN_FILENAME = os.path.join(
    DATA_DIR, "cleaned", "%d-%d.html"
)  # % (law_year, law_num)
PATCHED_FILENAME = os.path.join(
    DATA_DIR, "patched", "%d-%d.html"
)  # % (law_year, law_num)
PATCH_FILENAME = os.path.join(
    DATA_DIR, "patches", CURRENT_PARLIAMENT_VERSION, "%d-%d.html.patch"
)  # % (law_year, law_num)
XML_FILENAME = os.path.join(DATA_DIR, "xml", "%d.%s.xml")  # % (law_year, law_num)
XML_INDEX_FILENAME = os.path.join(DATA_DIR, "xml", "index.xml")
XML_REFERENCES_FILENAME = os.path.join(DATA_DIR, "xml", "references.xml")

ERRORMAP_FILENAME = os.path.join("data", "json-maps", "errormap.json")
