import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CURRENT_PARLIAMENT_VERSION = "154a"

DEBUG = True

DATA_DIR = os.path.join(BASE_DIR, "data")

# Feature knobs are only intended for incomplete functionality.
FEATURES = {
    "PARSE_MARKERS": True,
}

# Contains user-selected options by command line, so that they are available
# to different parts of the program.
options = {}
