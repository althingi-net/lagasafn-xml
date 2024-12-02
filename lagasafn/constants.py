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
XML_FILENAME = os.path.join(DATA_DIR, "xml", CURRENT_PARLIAMENT_VERSION, "%d.%s.xml")  # % (law_year, law_num)
XML_INDEX_FILENAME = os.path.join(DATA_DIR, "xml", CURRENT_PARLIAMENT_VERSION, "index.xml")
XML_REFERENCES_FILENAME = os.path.join(DATA_DIR, "xml", CURRENT_PARLIAMENT_VERSION, "references.xml")

ERRORMAP_FILENAME = os.path.join("data", "json-maps", CURRENT_PARLIAMENT_VERSION, "errormap.json")
STRAYTEXTMAP_FILENAME = os.path.join("data", "json-maps", CURRENT_PARLIAMENT_VERSION, "straytextmap.json")
SPLITMAP_FILENAME = os.path.join("data", "json-maps", CURRENT_PARLIAMENT_VERSION, "splitmap.json")
PROBLEMS_FILENAME = os.path.join(DATA_DIR, "xml", CURRENT_PARLIAMENT_VERSION, "problems.xml")
