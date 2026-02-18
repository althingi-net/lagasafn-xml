from dotenv import load_dotenv
from os import environ

load_dotenv()

def require_env(var_name: str):
    """
    Makes sure that a required value is configured.
    """
    value = environ.get(var_name, "")
    if value == "":
        raise Exception("Need environment variable configured: %s" % var_name)

    return value

# Don't run with debug turned on in production!
# We make the strict requirement that the literal, case-insensitive string
# "true" is used. We don't want a non-empty string like "false" or "0"
# evaluating as boolean `True`.
DEBUG = str(environ.get("DEBUG", "")).lower() == "true"

# Keep the secret key used in production secret!
SECRET_KEY = require_env("SECRET_KEY")

# Access token for API POST & PUT requests.
API_ACCESS_TOKEN = require_env("API_ACCESS_TOKEN")

if not DEBUG:
    ALLOWED_HOSTS = require_env("ALLOWED_HOSTS").split(",")

# Feature-knobs. They decide which optional features are active.
FEATURES = {
    "link_to_editor": True,
    "law_box": False,
    "show_adverts": False,
}

