from os import environ
from os import path
from dotenv import load_dotenv

load_dotenv()


BASE_DIR = path.dirname(path.dirname(path.abspath(__file__)))

CURRENT_PARLIAMENT_VERSION = "155"

DEBUG = True

DATA_DIR = path.join(BASE_DIR, "data")

# Feature knobs are only intended for incomplete functionality.
FEATURES = {
    "PARSE_MARKERS": True,  # FIXME: Feature-complete, knob should be removed.
    "PARSE_INTENTS": True,
    "PARSE_INTENTS_AI": False,
}

OPENAI_API_KEY = environ.get("OPENAI_API_KEY", "")

# Contains user-selected options by command line, so that they are available
# to different parts of the program.
options = {}
