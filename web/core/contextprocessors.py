from django.conf import settings


def globals(request):
    ctx = {
        "PROJECT_NAME": settings.PROJECT_NAME,
        "PROJECT_VERSION": settings.PROJECT_VERSION,
        "LEGAL_FRAMEWORK": settings.LEGAL_FRAMEWORK,
    }

    return ctx
