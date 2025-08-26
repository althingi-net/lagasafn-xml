from __future__ import unicode_literals

from django.apps import AppConfig
from django.core.cache import caches


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        # Clear cache on project startup.
        cache = caches["default"]
        cache.clear()
