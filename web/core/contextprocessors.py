from django.conf import settings
from django.core.cache import caches
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.models import LawManager


def globals(request):

    # Populate cache for things that are too heavy to run on every page load.
    # Will be cleared on project startup in `core.apps.ready`.
    cache = caches["default"]
    if cache.get("index") is None:
        cache.set("index", LawManager.index(CURRENT_PARLIAMENT_VERSION))

    ctx = {
        "PROJECT_NAME": settings.PROJECT_NAME,
        "PROJECT_VERSION": settings.PROJECT_VERSION,
        "LEGAL_FRAMEWORK": settings.LEGAL_FRAMEWORK,
        "FEATURES": settings.FEATURES,
        "CURRENT_PARLIAMENT_VERSION": CURRENT_PARLIAMENT_VERSION,
        "index": cache.get("index")
    }

    return ctx
