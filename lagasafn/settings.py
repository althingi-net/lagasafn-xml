from os import path

BASE_DIR = path.dirname(path.dirname(path.abspath(__file__)))

CURRENT_PARLIAMENT_VERSION = "154c"

DEBUG = True

DATA_DIR = path.join(BASE_DIR, "data")

# Feature knobs are only intended for incomplete functionality.
FEATURES = {
    "PARSE_MARKERS": True,
}

# Contains user-selected options by command line, so that they are available
# to different parts of the program.
options = {}
