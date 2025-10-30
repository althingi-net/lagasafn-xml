from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.settings import DATA_DIR
from os.path import join

# TODO: Make constants file less of a jungle.

ICELANDIC_DATE_REGEX = r"(\d{1,2})\. ([a-zúíáó]{1,9}) (\d{4})"

JSON_MAP_BASE_DIR = join(DATA_DIR, "json-maps")
PATCHES_BASE_DIR = join(DATA_DIR, "patches")
XML_BASE_DIR = join(DATA_DIR, "xml")
BILLS_BASE_DIR = join(DATA_DIR, "bills")

LAW_FILENAME_DIR = join(DATA_DIR, "original", "%s")  # % codex_version

LAW_FILENAME = join(
    LAW_FILENAME_DIR, "%d%s.html"
)  # % (codex_version, law_year, law_num)

CLEAN_FILENAME = join(DATA_DIR, "cleaned", "%d-%d.html")  # % (law_year, law_num)

PATCHED_FILENAME = join(DATA_DIR, "patched", "%d-%d.html")  # % (law_year, law_num)

PATCH_FILENAME = join(
    PATCHES_BASE_DIR, "%s", "%d-%d.html.patch"
)  # % (codex_version, law_year, law_num)

ADVERT_REMOTES_DIR = join(DATA_DIR, "adverts", "remote")
ADVERT_REMOTE_FILENAME = join(
    ADVERT_REMOTES_DIR, "%d.%d.remote.xml"
)  # (advert_year, advert_nr)

ADVERT_FIXED_DIR = join(DATA_DIR, "adverts", "fixed")
ADVERT_FIXED_FILENAME = join(
    ADVERT_FIXED_DIR, "%d.%d.fixed.xml"
)  # (advert_year, advert_nr)

ADVERT_DIR = join(DATA_DIR, "adverts", "xml")
ADVERT_FILENAME = join(ADVERT_DIR, "%d.%d.advert.xml")  # % (year, nr)

ADVERT_ORIGINAL_DIR = join(DATA_DIR, "adverts", "original")
ADVERT_ORIGINAL_FILENAME = join(
    ADVERT_ORIGINAL_DIR, "%d.%d.original.xml"
)  # % (year, nr)

ADVERT_INDEX_FILENAME = join(DATA_DIR, "adverts", "index.xml")

XML_FILENAME_DIR = join(XML_BASE_DIR, "%s")  # % codex_version
XML_FILENAME = join(
    XML_FILENAME_DIR, "%d.%s.xml"
)  # % (codex_version, law_year, law_num)
XML_INDEX_FILENAME = join(XML_BASE_DIR, "%s", "index.xml")  # % codex_version
XML_REFERENCES_FILENAME = join(XML_BASE_DIR, "%s", "references.xml")  # % codex_version

BILL_FILENAME_DIR = join(BILLS_BASE_DIR, "%s")  # % codex_version
BILL_FILENAME = join(
    BILL_FILENAME_DIR, "%d.%d.%s.xml"
)  # % (bill_num, law_year, law_num)

BILLMETA_FILENAME = join(BILL_FILENAME_DIR, "%d.meta.xml")  # % (bill_num)

ERRORMAP_FILENAME = join(JSON_MAP_BASE_DIR, "%s", "errormap.json")  # % codex_version
STRAYTEXTMAP_FILENAME = join(
    JSON_MAP_BASE_DIR, "%s", "straytextmap.json"
)  # % codex_version
SPLITMAP_FILENAME = join(JSON_MAP_BASE_DIR, "%s", "splitmap.json")  # % codex_version
PROBLEMS_FILENAME = join(XML_BASE_DIR, "%s", "problems.xml")  # % codex_version

XSD_FILENAME = join(DATA_DIR, "xsd", "%s.xsd")  # % root_tag_name
